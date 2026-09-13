#!/usr/bin/env python3
"""Root-owned transactional guard for the measured HyperLab Gaming Mode."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import pwd
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time


CONFIG = Path("/etc/privatestack/host-gaming-mode.json")
RUNTIME_DIR = Path("/run/hyperlab-gaming-mode")
STATE_PATH = RUNTIME_DIR / "state.json"
LOCK_PATH = RUNTIME_DIR / "transaction.lock"
SYSTEM_CPU_ROOT = Path("/sys/devices/system/cpu")
CGROUP_ROOT = Path("/sys/fs/cgroup")


class GamingModeError(RuntimeError):
    """A refused or failed Gaming Mode transition."""


class GuardSignal(RuntimeError):
    """Signal translated into normal cleanup control flow."""

    def __init__(self, signum: int):
        super().__init__(f"signal {signum}")
        self.signum = signum


def emit(event: str, **payload: object) -> None:
    record = {"event": event, **payload}
    print(json.dumps(record, sort_keys=True), flush=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def run_command(argv: list[str]) -> str:
    env = dict(os.environ)
    env["LC_ALL"] = "C"

    result = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise GamingModeError(
            f"command failed rc={result.returncode}: "
            f"{' '.join(argv)}: {stderr}"
        )

    return result.stdout.strip()


def parse_cpu_set(value: str) -> frozenset[int]:
    cpus: set[int] = set()

    for token in value.split(","):
        token = token.strip()

        if not token:
            continue

        if "-" in token:
            first_text, last_text = token.split("-", 1)
            first = int(first_text)
            last = int(last_text)

            if first > last:
                raise GamingModeError(f"invalid CPU range: {token}")

            cpus.update(range(first, last + 1))
        else:
            cpus.add(int(token))

    if not cpus:
        raise GamingModeError(f"empty CPU set: {value!r}")

    return frozenset(cpus)


def load_config() -> dict[str, object]:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GamingModeError(f"cannot read Gaming Mode config: {exc}") from exc

    required = {
        "schema_version",
        "operator_user",
        "expected_host_profile",
        "host_profile_report",
        "runtime_dir",
        "epp",
        "allowed_cpus",
        "system_effective_cpus",
        "user_effective_cpus",
        "machine_effective_cpus",
        "expected_epp_cpu_count",
        "domain",
        "vcpu_pins",
        "emulator_pin",
        "iothread_id",
        "iothread_pin",
    }

    if set(data) != required:
        raise GamingModeError(
            "Gaming Mode config fields do not match the reviewed schema"
        )

    if data["schema_version"] != 1:
        raise GamingModeError("unsupported Gaming Mode schema")

    if data["runtime_dir"] != str(RUNTIME_DIR):
        raise GamingModeError("runtime directory is not the reviewed fixed path")

    if data["epp"] != "performance":
        raise GamingModeError("only the measured performance EPP is accepted")

    if data["allowed_cpus"] != "0,1,4,5":
        raise GamingModeError("host CPU isolation drifted from measured policy")

    if int(data["expected_epp_cpu_count"]) != 8:
        raise GamingModeError("unexpected measured CPU count")

    parse_cpu_set(str(data["allowed_cpus"]))
    parse_cpu_set(str(data["system_effective_cpus"]))
    parse_cpu_set(str(data["user_effective_cpus"]))
    parse_cpu_set(str(data["machine_effective_cpus"]))
    parse_cpu_set(str(data["emulator_pin"]))
    parse_cpu_set(str(data["iothread_pin"]))

    vcpu_pins = data["vcpu_pins"]

    if not isinstance(vcpu_pins, dict):
        raise GamingModeError("vcpu_pins must be an object")

    if vcpu_pins != {"0": "2", "1": "6", "2": "3", "3": "7"}:
        raise GamingModeError("reviewed vCPU topology drifted")

    return data


def require_operator(config: dict[str, object]) -> int:
    if os.geteuid() != 0:
        raise GamingModeError("root helper must run as root")

    sudo_uid_text = os.environ.get("SUDO_UID")

    if sudo_uid_text is None:
        raise GamingModeError("root helper requires an explicit sudo caller")

    try:
        sudo_uid = int(sudo_uid_text)
    except ValueError as exc:
        raise GamingModeError("invalid SUDO_UID") from exc

    operator = pwd.getpwnam(str(config["operator_user"]))

    if sudo_uid != operator.pw_uid:
        raise GamingModeError("sudo caller is not the configured operator")

    return sudo_uid


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)

    info = RUNTIME_DIR.lstat()

    if not stat.S_ISDIR(info.st_mode):
        raise GamingModeError("runtime path is not a directory")

    if info.st_uid != 0:
        raise GamingModeError("runtime directory is not root-owned")

    os.chmod(RUNTIME_DIR, 0o755)


def acquire_lock():
    ensure_runtime_dir()

    handle = LOCK_PATH.open("a+", encoding="utf-8")

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise GamingModeError(
            "another Gaming Mode transaction is active"
        ) from exc

    return handle


def write_state(state_data: dict[str, object]) -> None:
    ensure_runtime_dir()

    fd, temp_name = tempfile.mkstemp(
        prefix=".state.",
        dir=RUNTIME_DIR,
        text=True,
    )

    try:
        os.fchmod(fd, 0o644)

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state_data, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_name, STATE_PATH)
    finally:
        temp = Path(temp_name)

        if temp.exists():
            temp.unlink()


def load_state() -> dict[str, object]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GamingModeError(f"cannot read saved Gaming Mode state: {exc}") from exc


def set_allowed_cpus(unit: str, value: str) -> None:
    run_command(
        [
            "systemctl",
            "set-property",
            "--runtime",
            unit,
            f"AllowedCPUs={value}",
        ]
    )


def get_allowed_cpus(unit: str) -> str:
    return run_command(
        [
            "systemctl",
            "show",
            unit,
            "-p",
            "AllowedCPUs",
            "--value",
        ]
    )


def effective_cpus(unit: str) -> str:
    return read_text(CGROUP_ROOT / unit / "cpuset.cpus.effective")


def host_profile(config: dict[str, object]) -> str:
    report = Path(str(config["host_profile_report"]))

    if not report.is_file() or report.is_symlink():
        raise GamingModeError("validated host profile report is unavailable")

    for line in report.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"host_profile:\s*([A-Za-z0-9_-]+)\s*", line)

        if match:
            return match.group(1)

    raise GamingModeError("host profile report has no host_profile field")


def validate_security_floor(config: dict[str, object]) -> None:
    if "hardened" not in platform.release():
        raise GamingModeError("host kernel is outside the hardened baseline")

    if read_text(Path("/proc/sys/kernel/randomize_va_space")) != "2":
        raise GamingModeError("host ASLR baseline is not active")

    unsafe = Path(
        "/sys/module/vfio_iommu_type1/parameters/allow_unsafe_interrupts"
    )

    if not unsafe.is_file():
        raise GamingModeError("VFIO unsafe-interrupt parameter is unavailable")

    if read_text(unsafe).upper() not in {"N", "0"}:
        raise GamingModeError("unsafe VFIO interrupts are enabled")

    current_profile = host_profile(config)

    if current_profile != config["expected_host_profile"]:
        raise GamingModeError(
            f"host profile mismatch: {current_profile!r}"
        )


def pin_rows(output: str) -> dict[str, frozenset[int]]:
    rows: dict[str, frozenset[int]] = {}

    for line in output.splitlines():
        match = re.fullmatch(
            r"\s*(\d+)\s+([0-9,-]+)\s*",
            line,
        )

        if match:
            rows[match.group(1)] = parse_cpu_set(match.group(2))

    return rows


def emulator_pin(output: str) -> frozenset[int]:
    for line in output.splitlines():
        match = re.fullmatch(r"\s*\*:\s*([0-9,-]+)\s*", line)

        if match:
            return parse_cpu_set(match.group(1))

    raise GamingModeError("cannot parse emulator affinity")


def validate_topology(config: dict[str, object]) -> None:
    domain = str(config["domain"])
    connection = "qemu:///system"

    state = run_command(
        ["virsh", "--connect", connection, "domstate", domain]
    ).lower()

    if state != "running":
        raise GamingModeError(f"{domain} must be running")

    current_vcpu = pin_rows(
        run_command(
            ["virsh", "--connect", connection, "vcpupin", domain]
        )
    )

    expected_vcpu = {
        str(index): parse_cpu_set(str(value))
        for index, value in dict(config["vcpu_pins"]).items()
    }

    if current_vcpu != expected_vcpu:
        raise GamingModeError(
            f"vCPU topology drifted: {current_vcpu!r}"
        )

    current_emulator = emulator_pin(
        run_command(
            ["virsh", "--connect", connection, "emulatorpin", domain]
        )
    )

    expected_emulator = parse_cpu_set(str(config["emulator_pin"]))

    if current_emulator != expected_emulator:
        raise GamingModeError(
            f"emulator affinity drifted: {current_emulator!r}"
        )

    iothreads = pin_rows(
        run_command(
            ["virsh", "--connect", connection, "iothreadinfo", domain]
        )
    )

    iothread_key = str(config["iothread_id"])
    expected_iothread = parse_cpu_set(str(config["iothread_pin"]))

    if iothreads.get(iothread_key) != expected_iothread:
        raise GamingModeError(
            f"I/O thread affinity drifted: {iothreads!r}"
        )


def epp_paths(config: dict[str, object]) -> list[Path]:
    def cpu_number(path: Path) -> int:
        match = re.fullmatch(r"cpu(\d+)", path.parent.parent.name)

        if not match:
            raise GamingModeError(f"unexpected EPP path: {path}")

        return int(match.group(1))

    paths = sorted(
        SYSTEM_CPU_ROOT.glob(
            "cpu[0-9]*/cpufreq/energy_performance_preference"
        ),
        key=cpu_number,
    )

    if len(paths) != int(config["expected_epp_cpu_count"]):
        raise GamingModeError(
            f"expected {config['expected_epp_cpu_count']} EPP files, "
            f"found {len(paths)}"
        )

    target = str(config["epp"])

    for path in paths:
        choices = path.parent / "energy_performance_available_preferences"

        if choices.is_file() and target not in read_text(choices).split():
            raise GamingModeError(
                f"{path} does not advertise EPP {target!r}"
            )

    return paths


def capture_state(
    config: dict[str, object],
    operator_uid: int,
) -> dict[str, object]:
    paths = epp_paths(config)

    return {
        "schema_version": 1,
        "guard_pid": os.getpid(),
        "operator_uid": operator_uid,
        "epp": [
            {
                "path": str(path),
                "value": read_text(path),
            }
            for path in paths
        ],
        "cpusets": {
            "system.slice": get_allowed_cpus("system.slice"),
            "user.slice": get_allowed_cpus("user.slice"),
        },
    }


def validate_candidate(config: dict[str, object]) -> None:
    target = str(config["epp"])

    actual_epp = {
        read_text(path)
        for path in epp_paths(config)
    }

    if actual_epp != {target}:
        raise GamingModeError(
            f"EPP candidate validation failed: {sorted(actual_epp)!r}"
        )

    checks = {
        "system.slice": str(config["system_effective_cpus"]),
        "user.slice": str(config["user_effective_cpus"]),
        "machine.slice": str(config["machine_effective_cpus"]),
    }

    for unit, expected in checks.items():
        actual = effective_cpus(unit)

        if parse_cpu_set(actual) != parse_cpu_set(expected):
            raise GamingModeError(
                f"{unit} effective CPUs expected {expected}, got {actual}"
            )

    validate_topology(config)


def apply_candidate(config: dict[str, object]) -> None:
    target = str(config["epp"])

    for path in epp_paths(config):
        path.write_text(target + "\n", encoding="utf-8")

    allowed = str(config["allowed_cpus"])

    set_allowed_cpus("system.slice", allowed)
    set_allowed_cpus("user.slice", allowed)

    time.sleep(1.0)
    validate_candidate(config)


def restore_state(state_data: dict[str, object]) -> tuple[bool, list[str]]:
    errors: list[str] = []

    for entry in list(state_data.get("epp", [])):
        path = Path(str(entry["path"]))
        expected = str(entry["value"])

        try:
            path.write_text(expected + "\n", encoding="utf-8")
        except OSError as exc:
            errors.append(f"restore {path}: {exc}")

    cpusets = dict(state_data.get("cpusets", {}))

    for unit in ("system.slice", "user.slice"):
        expected = str(cpusets.get(unit, ""))

        try:
            set_allowed_cpus(unit, expected)
        except GamingModeError as exc:
            errors.append(str(exc))

    time.sleep(0.1)

    for entry in list(state_data.get("epp", [])):
        path = Path(str(entry["path"]))
        expected = str(entry["value"])

        try:
            actual = read_text(path)
        except OSError as exc:
            errors.append(f"verify {path}: {exc}")
            continue

        if actual != expected:
            errors.append(
                f"restore mismatch {path}: "
                f"expected {expected!r}, got {actual!r}"
            )

    for unit in ("system.slice", "user.slice"):
        expected = str(cpusets.get(unit, ""))

        try:
            actual = get_allowed_cpus(unit)
        except GamingModeError as exc:
            errors.append(str(exc))
            continue

        if actual != expected:
            errors.append(
                f"restore mismatch {unit}: "
                f"expected {expected!r}, got {actual!r}"
            )

    if not errors:
        try:
            STATE_PATH.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"cannot remove restored state: {exc}")

    return not errors, errors


def signal_handler(signum: int, _frame: object) -> None:
    raise GuardSignal(signum)


def guard(config: dict[str, object]) -> int:
    operator_uid = require_operator(config)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)

    lock_handle = acquire_lock()

    with lock_handle:
        if STATE_PATH.exists():
            stale = load_state()
            restored, errors = restore_state(stale)

            emit(
                "stale-recovery",
                ok=restored,
                errors=errors,
            )

            if not restored:
                raise GamingModeError(
                    "cannot recover stale Gaming Mode state"
                )

        validate_security_floor(config)
        validate_topology(config)

        state_data = capture_state(config, operator_uid)
        write_state(state_data)

        result = 0

        try:
            apply_candidate(config)

            emit(
                "ready",
                epp=config["epp"],
                allowed_cpus=config["allowed_cpus"],
                domain=config["domain"],
            )

            sys.stdin.buffer.read()
            emit("workload-exit")
        except GuardSignal as exc:
            result = 128 + exc.signum
            emit("guard-signal", signum=exc.signum)
        except (GamingModeError, OSError) as exc:
            result = 70
            emit("apply-failure", error=str(exc))
        finally:
            restored, errors = restore_state(state_data)

            emit(
                "restore",
                ok=restored,
                errors=errors,
            )

            if not restored:
                result = 93

        return result


def recover(config: dict[str, object]) -> int:
    require_operator(config)

    lock_handle = acquire_lock()

    with lock_handle:
        if not STATE_PATH.exists():
            emit("recover", ok=True, stale_state=False)
            return 0

        state_data = load_state()
        restored, errors = restore_state(state_data)

        emit(
            "recover",
            ok=restored,
            stale_state=True,
            errors=errors,
        )

        return 0 if restored else 93


def self_test(config: dict[str, object]) -> int:
    parse_cpu_set(str(config["allowed_cpus"]))

    emit(
        "self-test",
        ok=True,
        schema_version=config["schema_version"],
        policy="transactional-runtime-only",
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Root guard for HyperLab Gaming Mode"
    )
    parser.add_argument(
        "operation",
        choices=("guard", "recover", "self-test"),
    )
    args = parser.parse_args()

    try:
        config = load_config()

        if args.operation == "guard":
            return guard(config)

        if args.operation == "recover":
            return recover(config)

        return self_test(config)
    except (GamingModeError, OSError, KeyError, ValueError) as exc:
        emit("error", error=str(exc))
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
