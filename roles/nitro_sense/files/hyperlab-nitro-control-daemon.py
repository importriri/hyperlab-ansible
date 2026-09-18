#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import signal
import socket
import stat
import struct
import time
from pathlib import Path
from typing import Any


HEX = re.compile(r"^[0-9a-fA-F]{6}$")
SO_PEERCRED_FORMAT = "3i"
SCOPES = {"runtime", "persistent"}

REQUEST_FIELDS = {
    "status": frozenset({"op"}),
    "set_fan": frozenset({"op", "cpu", "gpu", "scope"}),
    "set_battery_limiter": frozenset({"op", "enabled", "scope"}),
    "set_rgb": frozenset({"op", "zones", "brightness", "scope"}),
    "clear_persistent": frozenset({"op", "target"}),
}


class ProtocolError(Exception):
    pass


class Broker:
    def __init__(self, args: argparse.Namespace) -> None:
        self.socket_path = Path(args.socket)
        self.allowed_uid = pwd.getpwnam(args.user).pw_uid
        self.model = args.model
        self.fan_path = Path(args.fan_path)
        self.battery_path = Path(args.battery_path)
        self.rgb_path = Path(args.rgb_path)
        self.state_path = Path(args.state_path)
        self.baseline_fan = self._canonical_fan(args.baseline_fan)
        self.baseline_battery = args.baseline_battery
        self.baseline_rgb = self._canonical_rgb(args.baseline_rgb)
        self.baseline_rgb_managed = args.baseline_rgb_managed
        self.per_zone_enabled = args.per_zone_enabled
        self.max_request_bytes = args.max_request_bytes
        self.rgb_min_interval = args.rgb_min_interval_ms / 1000.0
        self.last_rgb_write = 0.0
        self.listener: socket.socket | None = None

    def _peer_uid(self, conn: socket.socket) -> int:
        raw = conn.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            struct.calcsize(SO_PEERCRED_FORMAT),
        )
        _pid, uid, _gid = struct.unpack(SO_PEERCRED_FORMAT, raw)
        return uid

    def _authorize(self, conn: socket.socket) -> None:
        uid = self._peer_uid(conn)
        if uid not in {0, self.allowed_uid}:
            raise ProtocolError("unauthorized Nitro operator")

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text().strip()
        except OSError as exc:
            raise ProtocolError(f"unavailable Nitro node: {path}") from exc

    @staticmethod
    def _write_verify(path: Path, desired: str) -> str:
        # Hardware paths are fixed by the root-owned unit; the JSON protocol
        # never accepts a caller-supplied path.
        try:
            fd = os.open(
                path,
                os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except OSError as exc:
            raise ProtocolError(f"Nitro node is not writable: {path}") from exc

        try:
            os.write(fd, (desired + "\n").encode())
        finally:
            os.close(fd)

        observed = Broker._read(path)

        if observed != desired:
            raise ProtocolError(
                f"Nitro node refused value: expected {desired}, observed {observed}"
            )

        return observed

    @staticmethod
    def _canonical_fan(value: str) -> str:
        parts = value.split(",")

        if len(parts) != 2:
            raise ProtocolError("invalid baseline fan state")

        try:
            cpu, gpu = [int(item) for item in parts]
        except ValueError as exc:
            raise ProtocolError("invalid baseline fan state") from exc

        if not (0 <= cpu <= 100 and 0 <= gpu <= 100):
            raise ProtocolError("invalid baseline fan state")

        return f"{cpu},{gpu}"

    @staticmethod
    def _canonical_rgb(value: str) -> str:
        parts = value.split(",")

        if len(parts) != 5:
            raise ProtocolError("invalid baseline RGB state")

        zones = [item.lower() for item in parts[:4]]

        if any(HEX.fullmatch(item) is None for item in zones):
            raise ProtocolError("invalid baseline RGB state")

        try:
            brightness = int(parts[4])
        except ValueError as exc:
            raise ProtocolError("invalid baseline RGB brightness") from exc

        if not 0 <= brightness <= 100:
            raise ProtocolError("invalid baseline RGB brightness")

        return ",".join([*zones, str(brightness)])

    @staticmethod
    def _integer(value: Any, name: str) -> int:
        if type(value) is not int or not 0 <= value <= 100:
            raise ProtocolError(f"{name} must be an integer in 0..100")
        return value

    @staticmethod
    def _operation(request: dict[str, Any]) -> str:
        op = request.get("op")

        if not isinstance(op, str) or op not in REQUEST_FIELDS:
            raise ProtocolError("unsupported operation")

        expected = REQUEST_FIELDS[op]
        observed = frozenset(request)

        if observed != expected:
            raise ProtocolError(
                f"invalid request fields for {op}"
            )

        return op

    @staticmethod
    def _scope(request: dict[str, Any]) -> str:
        scope = request.get("scope")

        if scope not in SCOPES:
            raise ProtocolError("scope must be runtime or persistent")

        return str(scope)

    def _load_state(self) -> dict[str, Any]:
        try:
            entry = self.state_path.lstat()
        except FileNotFoundError:
            return {"version": 1}

        if not stat.S_ISREG(entry.st_mode):
            raise ProtocolError("persistent state is not a regular file")

        if entry.st_uid != os.geteuid():
            raise ProtocolError(
                "persistent state owner does not match broker identity"
            )

        if stat.S_IMODE(entry.st_mode) != 0o600:
            raise ProtocolError("persistent state must be mode 0600")

        try:
            state = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtocolError("invalid persistent Nitro state") from exc

        if not isinstance(state, dict) or state.get("version") != 1:
            raise ProtocolError("unsupported persistent Nitro state")

        allowed = {"version", "fan", "battery_limiter", "per_zone"}

        if set(state) - allowed:
            raise ProtocolError("unknown persistent Nitro fields")

        fan = state.get("fan")
        if fan is not None:
            parts = fan.split(",") if isinstance(fan, str) else []
            if len(parts) != 2:
                raise ProtocolError("invalid persistent fan state")

            try:
                cpu, gpu = [int(value) for value in parts]
            except ValueError as exc:
                raise ProtocolError("invalid persistent fan state") from exc

            if not (0 <= cpu <= 100 and 0 <= gpu <= 100):
                raise ProtocolError("invalid persistent fan state")

            if fan != f"{cpu},{gpu}":
                raise ProtocolError("non-canonical persistent fan state")

        battery = state.get("battery_limiter")
        if battery is not None and type(battery) is not bool:
            raise ProtocolError("invalid persistent battery state")

        rgb = state.get("per_zone")
        if rgb is not None:
            parts = rgb.split(",") if isinstance(rgb, str) else []

            if len(parts) != 5:
                raise ProtocolError("invalid persistent RGB state")

            if any(HEX.fullmatch(value) is None for value in parts[:4]):
                raise ProtocolError("invalid persistent RGB state")

            try:
                brightness = int(parts[4])
            except ValueError as exc:
                raise ProtocolError("invalid persistent RGB brightness") from exc

            if not 0 <= brightness <= 100:
                raise ProtocolError("invalid persistent RGB brightness")

        return state

    def _save_state(self, state: dict[str, Any]) -> None:
        parent = self.state_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        temporary = parent / (
            f".{self.state_path.name}.{os.getpid()}.{time.time_ns()}"
        )

        payload = (
            json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n"
        )

        fd = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | os.O_NOFOLLOW,
            0o600,
        )

        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            os.chmod(temporary, 0o600)
            os.replace(temporary, self.state_path)

            dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _persistence_payload(state: dict[str, Any]) -> dict[str, Any]:
        saved = {
            "fan": state.get("fan"),
            "battery_limiter": state.get("battery_limiter"),
            "per_zone": state.get("per_zone"),
        }

        return {
            "supported": True,
            "scope_default": "runtime",
            "saved": saved,
            "overrides": [
                key for key, value in saved.items()
                if value is not None
            ],
        }

    def _scoped_write(
        self,
        path: Path,
        desired: str,
        scope: str,
        state_key: str,
        saved_value: Any,
    ) -> str:
        previous = self._read(path)
        observed = self._write_verify(path, desired)

        if scope == "runtime":
            return observed

        state = self._load_state()
        state[state_key] = saved_value

        try:
            self._save_state(state)
        except Exception:
            self._write_verify(path, previous)
            raise

        return observed

    def _status(self) -> dict[str, Any]:
        rgb = None

        if self.per_zone_enabled and self.rgb_path.exists():
            rgb = self._read(self.rgb_path)

        state = self._load_state()

        return {
            "model": self.model,
            "capabilities": {
                "fan": self.fan_path.exists(),
                "battery_limiter": self.battery_path.exists(),
                "per_zone": self.per_zone_enabled and self.rgb_path.exists(),
                "effect": False,
            },
            "runtime": {
                "fan": self._read(self.fan_path),
                "battery_limiter": self._read(self.battery_path) == "1",
                "per_zone": rgb,
            },
            "persistence": self._persistence_payload(state),
        }

    def _set_fan(self, request: dict[str, Any]) -> dict[str, Any]:
        cpu = self._integer(request["cpu"], "cpu")
        gpu = self._integer(request["gpu"], "gpu")
        scope = self._scope(request)
        desired = f"{cpu},{gpu}"

        observed = self._scoped_write(
            self.fan_path,
            desired,
            scope,
            "fan",
            desired,
        )

        return {"fan": observed, "scope": scope}

    def _set_battery(self, request: dict[str, Any]) -> dict[str, Any]:
        enabled = request["enabled"]

        if type(enabled) is not bool:
            raise ProtocolError("enabled must be boolean")

        scope = self._scope(request)
        desired = "1" if enabled else "0"

        observed = self._scoped_write(
            self.battery_path,
            desired,
            scope,
            "battery_limiter",
            enabled,
        )

        return {
            "battery_limiter": observed == "1",
            "scope": scope,
        }

    def _set_rgb(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.per_zone_enabled:
            raise ProtocolError("per-zone RGB is unavailable")

        zones = request["zones"]

        if not isinstance(zones, list) or len(zones) != 4:
            raise ProtocolError("zones must contain exactly four values")

        normalized = []

        for value in zones:
            if not isinstance(value, str) or HEX.fullmatch(value) is None:
                raise ProtocolError("invalid RRGGBB value")
            normalized.append(value.lower())

        brightness = self._integer(request["brightness"], "brightness")
        scope = self._scope(request)

        elapsed = time.monotonic() - self.last_rgb_write

        if elapsed < self.rgb_min_interval:
            raise ProtocolError("RGB rate limit active")

        desired = ",".join(normalized) + f",{brightness}"

        observed = self._scoped_write(
            self.rgb_path,
            desired,
            scope,
            "per_zone",
            desired,
        )

        self.last_rgb_write = time.monotonic()

        return {"per_zone": observed, "scope": scope}

    def _clear_persistent(self, request: dict[str, Any]) -> dict[str, Any]:
        target = request["target"]

        mapping = {
            "all": None,
            "fan": "fan",
            "battery": "battery_limiter",
            "rgb": "per_zone",
        }

        if target not in mapping:
            raise ProtocolError("invalid persistent target")

        previous_state = self._load_state()
        state_existed = self.state_path.exists()
        next_state = dict(previous_state)

        if target == "all":
            next_state = {"version": 1}
        else:
            next_state.pop(mapping[target], None)

        restores: list[tuple[Path, str]] = []

        if target in {"all", "fan"}:
            restores.append((self.fan_path, self.baseline_fan))

        if target in {"all", "battery"}:
            restores.append((self.battery_path, self.baseline_battery))

        if (
            target in {"all", "rgb"}
            and self.per_zone_enabled
            and self.baseline_rgb_managed
        ):
            restores.append((self.rgb_path, self.baseline_rgb))

        previous_runtime: list[tuple[Path, str]] = []

        try:
            for path, desired in restores:
                previous_runtime.append((path, self._read(path)))
                self._write_verify(path, desired)

            self._save_state(next_state)
        except (OSError, ProtocolError) as exc:
            rollback_failed = False

            for path, previous in reversed(previous_runtime):
                try:
                    self._write_verify(path, previous)
                except ProtocolError:
                    rollback_failed = True

            try:
                if state_existed:
                    self._save_state(previous_state)
                else:
                    try:
                        self.state_path.unlink()
                    except FileNotFoundError:
                        pass
            except OSError:
                rollback_failed = True

            if rollback_failed:
                raise ProtocolError(
                    "persistent clear failed and rollback was incomplete"
                ) from exc

            raise

        return {
            "cleared": target,
            "persistence": self._persistence_payload(next_state),
        }

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        op = self._operation(request)

        if op == "status":
            payload = self._status()
        elif op == "set_fan":
            payload = self._set_fan(request)
        elif op == "set_battery_limiter":
            payload = self._set_battery(request)
        elif op == "set_rgb":
            payload = self._set_rgb(request)
        elif op == "clear_persistent":
            payload = self._clear_persistent(request)
        else:
            raise AssertionError("unreachable operation")

        return {"ok": True, "status": payload}

    def _receive(self, conn: socket.socket) -> dict[str, Any]:
        data = bytearray()

        while len(data) <= self.max_request_bytes:
            part = conn.recv(
                min(1024, self.max_request_bytes + 1 - len(data))
            )

            if not part:
                break

            data.extend(part)

            if b"\n" in part:
                break

        if not data or len(data) > self.max_request_bytes:
            raise ProtocolError("invalid request size")

        line, separator, trailing = bytes(data).partition(b"\n")

        if not separator or trailing.strip():
            raise ProtocolError("exactly one newline-terminated request required")

        try:
            request = json.loads(line.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("invalid JSON request") from exc

        if not isinstance(request, dict):
            raise ProtocolError("request must be a JSON object")

        return request

    @staticmethod
    def _reply(conn: socket.socket, payload: dict[str, Any]) -> None:
        conn.sendall((json.dumps(payload, sort_keys=True) + "\n").encode())

    def serve(self) -> None:
        runtime_dir = self.socket_path.parent

        if not runtime_dir.is_dir():
            raise RuntimeError("runtime directory is missing")

        if os.path.lexists(self.socket_path):
            previous = os.lstat(self.socket_path)

            if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid != 0:
                raise RuntimeError("refusing unsafe socket path")

            self.socket_path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener = listener
        listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o660)
        listener.listen(8)

        while True:
            conn, _ = listener.accept()

            with conn:
                try:
                    self._authorize(conn)
                    request = self._receive(conn)
                    reply = self.dispatch(request)
                except (ProtocolError, OSError, TimeoutError) as exc:
                    reply = {"ok": False, "error": str(exc)}

                self._reply(conn, reply)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--socket", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fan-path", required=True)
    parser.add_argument("--battery-path", required=True)
    parser.add_argument("--rgb-path", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--baseline-fan", required=True)
    parser.add_argument(
        "--baseline-battery",
        choices=("0", "1"),
        required=True,
    )
    parser.add_argument("--baseline-rgb", required=True)
    parser.add_argument("--baseline-rgb-managed", action="store_true")
    parser.add_argument("--per-zone-enabled", action="store_true")
    parser.add_argument("--rgb-min-interval-ms", type=int, required=True)
    parser.add_argument("--max-request-bytes", type=int, required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    broker = Broker(args)

    def stop(_signum: int, _frame: object) -> None:
        if broker.listener is not None:
            broker.listener.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    broker.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
