#!/usr/bin/env python3
"""Narrow privileged broker for validated Acer Nitro runtime controls."""
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


HEX_COLOUR = re.compile(r"^[0-9a-fA-F]{6}$")
SO_PEERCRED_FORMAT = "3i"

REQUEST_FIELDS = {
    "status": frozenset({"op"}),
    "set_fan": frozenset({"op", "cpu", "gpu"}),
    "set_battery_limiter": frozenset({"op", "enabled"}),
    "set_rgb": frozenset({"op", "zones", "brightness"}),
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
        # Socket permissions are the first boundary; peer credentials prevent a
        # second account in the same group from inheriting hardware authority.
        uid = self._peer_uid(conn)
        if uid not in {0, self.allowed_uid}:
            raise ProtocolError("peer is not the configured HyperLab operator")

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ProtocolError(f"required Nitro node is unavailable: {path}") from exc

    @staticmethod
    def _write_verify(path: Path, desired: str) -> str:
        # Paths come only from the root-owned systemd unit. The protocol never
        # accepts a caller-supplied path, which keeps this from becoming a
        # generic privileged sysfs writer.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
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
    def _integer(value: Any, name: str, low: int, high: int) -> int:
        if type(value) is not int or not low <= value <= high:
            raise ProtocolError(f"{name} must be an integer in {low}..{high}")
        return value

    @staticmethod
    def _operation(request: dict[str, Any]) -> str:
        op = request.get("op")
        if not isinstance(op, str) or op not in REQUEST_FIELDS:
            raise ProtocolError("unsupported operation")

        expected = REQUEST_FIELDS[op]
        observed = frozenset(request)
        if observed != expected:
            missing = sorted(expected - observed)
            extra = sorted(observed - expected)
            details: list[str] = []
            if missing:
                details.append("missing " + ",".join(missing))
            if extra:
                details.append("unexpected " + ",".join(extra))
            raise ProtocolError(
                f"invalid request fields for {op}: " + "; ".join(details)
            )
        return op

    def _status(self) -> dict[str, Any]:
        fan = self._read(self.fan_path)
        battery = self._read(self.battery_path)

        rgb: str | None = None
        if self.per_zone_enabled and self.rgb_path.exists():
            rgb = self._read(self.rgb_path)

        return {
            "model": self.model,
            "capabilities": {
                "fan": self.fan_path.exists(),
                "battery_limiter": self.battery_path.exists(),
                "per_zone": self.per_zone_enabled and self.rgb_path.exists(),
                # Firmware effects stay outside this broker until that distinct
                # WMI path receives its own physical hardware campaign.
                "effect": False,
            },
            "runtime": {
                "fan": fan,
                "battery_limiter": battery == "1",
                "per_zone": rgb,
            },
            # Runtime controls never rewrite Ansible-owned boot policy. A reboot
            # returns to the role's reviewed defaults.
            "persistence": "runtime-only",
        }

    def _set_fan(self, request: dict[str, Any]) -> dict[str, Any]:
        cpu = self._integer(request.get("cpu"), "cpu", 0, 100)
        gpu = self._integer(request.get("gpu"), "gpu", 0, 100)
        return {"fan": self._write_verify(self.fan_path, f"{cpu},{gpu}")}

    def _set_battery(self, request: dict[str, Any]) -> dict[str, Any]:
        enabled = request.get("enabled")
        if type(enabled) is not bool:
            raise ProtocolError("enabled must be boolean")
        observed = self._write_verify(self.battery_path, "1" if enabled else "0")
        return {"battery_limiter": observed == "1"}

    def _set_rgb(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.per_zone_enabled:
            raise ProtocolError("per-zone RGB is not accepted for this model")

        zones = request.get("zones")
        if not isinstance(zones, list) or len(zones) != 4:
            raise ProtocolError("zones must contain exactly four RRGGBB values")

        normalized: list[str] = []
        for colour in zones:
            if not isinstance(colour, str) or HEX_COLOUR.fullmatch(colour) is None:
                raise ProtocolError("each zone must be exactly six hexadecimal digits")
            normalized.append(colour.lower())

        brightness = self._integer(request.get("brightness"), "brightness", 0, 100)

        elapsed = time.monotonic() - self.last_rgb_write
        if elapsed < self.rgb_min_interval:
            retry_ms = int((self.rgb_min_interval - elapsed) * 1000) + 1
            raise ProtocolError(f"RGB rate limit active; retry after {retry_ms} ms")

        desired = ",".join(normalized) + f",{brightness}"
        observed = self._write_verify(self.rgb_path, desired)
        self.last_rgb_write = time.monotonic()
        return {"per_zone": observed}

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        # Reject shape drift before any operation can read or write hardware.
        # A narrow privileged protocol must not silently accept future-looking
        # or caller-invented fields that were never part of its reviewed schema.
        op = self._operation(request)
        if op == "status":
            payload = self._status()
        elif op == "set_fan":
            payload = self._set_fan(request)
        elif op == "set_battery_limiter":
            payload = self._set_battery(request)
        elif op == "set_rgb":
            payload = self._set_rgb(request)
        else:
            raise AssertionError("validated operation has no dispatcher")
        return {"ok": True, "status": payload}

    def _receive(self, conn: socket.socket) -> dict[str, Any]:
        chunks = bytearray()
        while len(chunks) <= self.max_request_bytes:
            part = conn.recv(min(1024, self.max_request_bytes + 1 - len(chunks)))
            if not part:
                break
            chunks.extend(part)
            if b"\n" in part:
                break

        if not chunks or len(chunks) > self.max_request_bytes:
            raise ProtocolError("request is empty or too large")
        if b"\n" not in chunks:
            raise ProtocolError("request must end with a newline")

        first_line, _separator, trailing = bytes(chunks).partition(b"\n")
        if trailing.strip():
            raise ProtocolError("one request is allowed per connection")

        try:
            request = json.loads(first_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("request must be one UTF-8 JSON object") from exc
        if not isinstance(request, dict):
            raise ProtocolError("request must be a JSON object")
        return request

    @staticmethod
    def _reply(conn: socket.socket, payload: dict[str, Any]) -> None:
        conn.sendall((json.dumps(payload, sort_keys=True) + "\n").encode())

    def serve(self) -> None:
        runtime_dir = self.socket_path.parent
        if not runtime_dir.is_dir():
            raise RuntimeError(f"systemd runtime directory is missing: {runtime_dir}")

        if os.path.lexists(self.socket_path):
            previous = os.lstat(self.socket_path)
            if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid != 0:
                raise RuntimeError(
                    f"refusing non-root or non-socket runtime path: {self.socket_path}"
                )
            self.socket_path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener = listener
        listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o660)
        listener.listen(8)

        while True:
            conn, _address = listener.accept()
            with conn:
                conn.settimeout(2.0)
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
