#!/usr/bin/env python3
"""Contract for the read-only shared HyperLab Quickshell status core."""

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
QML = "roles/host_desktop_common/files/quickshell/hyperlab/"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab Quickshell readonly runtime contract: "
            + message
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check_network_bridge() -> None:
    source = text("roles/host_desktop_sway/files/privatestack-hyperlab.sh")
    rows = [
        {"name": "fixture-up", "state": "active", "subnet": "192.0.2.0/26",
         "forward": "nat", "trust": 3},
        {"name": "fixture-down", "state": "inactive", "subnet": None,
         "forward": None, "trust": None},
        {"name": "fixture-absent", "state": "missing", "subnet": "198.51.100.0/24",
         "forward": "isolated", "trust": 0},
    ]
    with tempfile.TemporaryDirectory(prefix="hyperlab-network-bridge-") as raw:
        directory = Path(raw)
        cli = directory / "cli"
        trace = directory / "trace.jsonl"
        cli.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                       "with open(os.environ['NETWORK_TRACE'], 'a') as stream:\n"
                       "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                       "print(os.environ['NETWORK_OUTPUT'])\n"
                       "sys.exit(int(os.environ['NETWORK_EXIT']))\n")
        cli.chmod(0o755)
        bridge = directory / "bridge.sh"
        needle = "declare -r cli=/usr/local/bin/hyperlabctl"
        require(source.count(needle) == 1, "bridge fixture cannot isolate CLI")
        bridge.write_text(source.replace(needle, "declare -r cli=" + shlex.quote(str(cli))))
        for label, payload, code in (
            ("success", rows, 0), ("empty", [], 0),
            ("CLI failure", rows, 2), ("empty output", "", 0),
            ("missing CLI", "", 0),
        ):
            if label == "missing CLI":
                cli.unlink()
            trace.write_text("")
            result = subprocess.run(["bash", str(bridge), "network-inventory"],
                env={**os.environ, "NETWORK_TRACE": str(trace),
                     "NETWORK_OUTPUT": json.dumps(payload) if isinstance(payload, list) else payload,
                     "NETWORK_EXIT": str(code)}, capture_output=True, text=True,
                timeout=10, check=False)
            calls = [json.loads(line) for line in trace.read_text().splitlines()]
            require(calls == ([] if label == "missing CLI" else [["--json", "net", "list"]]),
                    f"network inventory exact read-only argv changed: {calls}")
            require(result.returncode == 0 and not result.stderr,
                    f"network bridge fallback process failed: {label}")
            parsed = json.loads(result.stdout)
            if label in ("success", "empty"):
                require(parsed == payload, f"network bridge altered rows: {label}")
            else:
                require(isinstance(parsed, dict) and parsed.get("class") == "error",
                        f"network bridge failure became inventory: {label}")


def main() -> int:
    check_network_bridge()

    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]

    require(
        stage["read_only_runtime_data_enabled"] is True,
        "read-only runtime data gate is not enabled",
    )
    require(
        stage["read_only_status_bridge"]
        == "/usr/local/bin/privatestack-hyperlab",
        "shell status bridge changed",
    )
    require(
        stage["trust_update_transport"] == "event-stream",
        "trust stopped being event-driven",
    )
    require(
        stage["slow_poll_seconds"] == 30,
        "slow status polling cadence changed",
    )

    state_qml = text(QML + "ShellState.qml")
    bar = text(QML + "HyperLabBar.qml")
    machine_stage = text(QML + "MachineStage.qml")
    context = text(QML + "ContextCluster.qml")
    identity = text(QML + "IdentityMark.qml")
    gpu = text(QML + "GpuBadge.qml")

    for marker in (
        "import Quickshell.Io",
        "SystemClock {",
        "Process {",
        "SplitParser {",
        '"/usr/local/bin/privatestack-hyperlab"',
        '"watch"',
        '"trust"',
        '"ram"',
        '"gpu"',
        '"vms"',
        "interval: 30000",
        "applyTrustPayload(data)",
    ):
        require(
            marker in state_qml,
            f"required runtime marker missing: {marker}",
        )

    for marker, corpus in (
        ('text: "HyperLab"', identity),
        ("badge.claim.claimed", gpu),
        (
            "provenanceColor(badge.claim.identity)",
            gpu,
        ),
        (
            "claim: bar.shellState.trustClaim",
            bar,
        ),
        (
            "payload: bar.shellState.gpuPayload",
            bar,
        ),
        (
            "shellState.machines",
            machine_stage,
        ),
        (
            "cluster.context",
            context,
        ),
    ):
        require(
            marker in corpus,
            f"required presentation wiring missing: {marker}",
        )

    shared_qml = "\n".join(
        text(QML + name)
        for name in stage["surface_files"]
    )

    for forbidden in (
        "Quickshell.Hyprland",
        "Quickshell.I3",
        "hyprctl",
        "swaymsg",
        "sudo",
        "pkexec",
        "/sys/",
        "execDetached",
        "Quickshell.execDetached",
        '["sh", "-c"',
        '["bash", "-c"',
        "MouseArea",
    ):
        require(
            forbidden not in shared_qml,
            f"forbidden shell behavior appeared: {forbidden}",
        )

    require(
        state_qml.count('"watch"') == 1
        and state_qml.count('"trust"') >= 1,
        "trust stream command is no longer singular",
    )

    require(
        "interval: 1000" not in state_qml
        and "interval: 5000" not in state_qml,
        "read-only status core gained aggressive polling",
    )

    print(
        "HyperLab shared Quickshell read-only runtime contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
