#!/usr/bin/env python3
"""Contract for HyperLab launcher/compositor provenance binding."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
HYPERLABCTL_ROOT = ROOT / "tools/hyperlabctl"

sys.path.insert(0, str(HYPERLABCTL_ROOT))

surface_registry = importlib.import_module(
    "hyperlabctl.surface_registry"
)

OPEN = (
    HYPERLABCTL_ROOT
    / "hyperlabctl/commands/open.py"
)

ADAPTER = (
    ROOT
    / "roles/host_desktop_common/files"
    / "privatestack-compositor-adapter.sh"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab runtime provenance binding contract: "
            + message
        )


def write_fake_proc(
    proc_root: Path,
    *,
    pid: int,
    start_ticks: str,
) -> None:
    process = proc_root / str(pid)
    process.mkdir(parents=True, exist_ok=True)

    # /proc/PID/stat:
    # remainder[19] after the closing ')' is original field 22/starttime.
    tail = [
        "S",
        "1",
        "1",
        "1",
        "0",
        "-1",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        start_ticks,
        "0",
        "0",
    ]

    (process / "stat").write_text(
        f"{pid} (hyperlabctl) "
        + " ".join(tail)
        + "\n",
        encoding="utf-8",
    )


def write_fake_command(
    path: Path,
    body: str,
) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        + body,
        encoding="utf-8",
    )
    path.chmod(0o755)


def run_adapter(
    *,
    backend: str,
    operation: str,
    bin_dir: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()

    env["PATH"] = (
        f"{bin_dir}:{env['PATH']}"
    )

    env["HYPERLAB_COMPOSITOR_BACKEND"] = backend

    env.pop(
        "HYPERLAB_SESSION_LIFECYCLE_MANAGED",
        None,
    )

    return subprocess.run(
        [
            str(ADAPTER),
            operation,
        ],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
        timeout=7,
    )


def verify_launcher_source() -> None:
    source = OPEN.read_text(
        encoding="utf-8"
    )

    require(
        (
            "from ..surface_registry import "
            "register_managed_surface"
        )
        in source,
        "launcher does not import registry publisher",
    )

    require(
        'managed_surface_kind = "looking-glass"'
        in source,
        "Looking Glass is not registered",
    )

    require(
        'managed_surface_kind = "spice-console"'
        in source,
        "SPICE console is not registered",
    )

    require(
        "_register_surface_provenance("
        in source,
        "launcher lacks provenance registration helper",
    )

    registration = source.find(
        "_register_surface_provenance(\n"
        "                ctx,"
    )

    execution = source.find(
        "os.execv(executable"
    )

    require(
        registration >= 0,
        "managed registration call missing",
    )

    require(
        execution >= 0,
        "managed exec call missing",
    )

    require(
        registration < execution,
        "managed provenance is registered after exec",
    )


def verify_registry() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-t6d-registry-"
    ) as temp_name:
        temp = Path(temp_name)

        runtime = temp / "runtime"
        runtime.mkdir(mode=0o700)

        proc_root = temp / "proc"
        proc_root.mkdir()

        specs = temp / "vm-specs"
        specs.mkdir()

        dev_spec = specs / "arch-dev-vfio.yml"

        dev_spec.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "name": "arch-dev-vfio",
                    "image": "arch",
                    "device_profile": "vfio",
                    "network_profile": "dev",
                    "looking_glass": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        pid = 48123
        start_ticks = "123456789"

        write_fake_proc(
            proc_root,
            pid=pid,
            start_ticks=start_ticks,
        )

        registry_path = (
            surface_registry.register_managed_surface(
                spec_path=dev_spec,
                domain="arch-dev-vfio",
                surface_kind="looking-glass",
                executable=(
                    "/usr/local/bin/"
                    "looking-glass-client"
                ),
                runtime_root=runtime,
                proc_root=proc_root,
                pid=pid,
            )
        )

        require(
            registry_path
            == (
                runtime
                / "hyperlab"
                / "surface-provenance.json"
            ),
            "registry path changed",
        )

        directory_info = registry_path.parent.lstat()
        file_info = registry_path.lstat()

        require(
            stat.S_ISDIR(directory_info.st_mode),
            "registry parent is not directory",
        )

        require(
            stat.S_IMODE(directory_info.st_mode)
            == 0o700,
            "registry parent mode is not 0700",
        )

        require(
            stat.S_ISREG(file_info.st_mode)
            and not stat.S_ISLNK(file_info.st_mode),
            "registry is not a real regular file",
        )

        require(
            stat.S_IMODE(file_info.st_mode)
            == 0o600,
            "registry mode is not 0600",
        )

        payload = json.loads(
            registry_path.read_text(
                encoding="utf-8"
            )
        )

        require(
            set(payload)
            == {"version", "entries"},
            "registry top-level shape changed",
        )

        require(
            payload["version"] == 1,
            "registry version changed",
        )

        require(
            len(payload["entries"]) == 1,
            "unexpected registry entry count",
        )

        entry = payload["entries"][0]

        require(
            entry["pid"] == pid,
            "registered PID changed",
        )

        require(
            entry["process_start_ticks"]
            == start_ticks,
            "registered process start-time changed",
        )

        require(
            entry["executable"]
            == (
                "/usr/local/bin/"
                "looking-glass-client"
            ),
            "registered executable changed",
        )

        require(
            entry["surface_kind"]
            == "looking-glass",
            "registered surface type changed",
        )

        require(
            entry["domain"]
            == "arch-dev-vfio",
            "registered VM domain changed",
        )

        require(
            entry["registered_by"]
            == "hyperlabctl",
            "unreviewed registrar gained authority",
        )

        expected_hash = hashlib.sha256(
            dev_spec.read_bytes()
        ).hexdigest()

        require(
            entry["spec_sha256"]
            == expected_hash,
            "VM spec SHA256 was not pinned",
        )

        # Re-registering the same process must replace rather than duplicate.
        second = (
            surface_registry.register_managed_surface(
                spec_path=dev_spec,
                domain="arch-dev-vfio",
                surface_kind="looking-glass",
                executable=(
                    "/usr/local/bin/"
                    "looking-glass-client"
                ),
                runtime_root=runtime,
                proc_root=proc_root,
                pid=pid,
            )
        )

        replay = json.loads(
            second.read_text(
                encoding="utf-8"
            )
        )

        require(
            len(replay["entries"]) == 1,
            "replay duplicated the same process registration",
        )

        # A stale process must be pruned on the next managed registration.
        shutil.rmtree(
            proc_root / str(pid)
        )

        clean_spec = specs / "win11clean-valley.yml"

        clean_spec.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "name": "win11clean-valley",
                    "image": "win11clean",
                    "device_profile": "vfio",
                    "network_profile": "clean",
                    "looking_glass": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        clean_pid = 48124

        write_fake_proc(
            proc_root,
            pid=clean_pid,
            start_ticks="123456790",
        )

        surface_registry.register_managed_surface(
            spec_path=clean_spec,
            domain="win11clean-valley",
            surface_kind="looking-glass",
            executable=(
                "/usr/local/bin/"
                "looking-glass-client"
            ),
            runtime_root=runtime,
            proc_root=proc_root,
            pid=clean_pid,
        )

        cleaned = json.loads(
            registry_path.read_text(
                encoding="utf-8"
            )
        )

        require(
            len(cleaned["entries"]) == 1,
            "stale process registration was not pruned",
        )

        require(
            cleaned["entries"][0]["pid"]
            == clean_pid,
            "wrong registration survived stale pruning",
        )


def verify_compositor_snapshot() -> None:
    adapter_source = ADAPTER.read_text(
        encoding="utf-8"
    )

    for marker in (
        "focused-window-json",
        "focused-window-watch",
        "focused_sway_json",
        "focused_hyprland_json",
        "focused_watch_sway",
        "focused_watch_hyprland",
        ".socket2.sock",
    ):
        require(
            marker in adapter_source,
            f"compositor primitive missing: {marker}",
        )

    with tempfile.TemporaryDirectory(
        prefix="hyperlab-t6d-adapter-"
    ) as temp_name:
        temp = Path(temp_name)

        bin_dir = temp / "bin"
        bin_dir.mkdir()

        write_fake_command(
            bin_dir / "swaymsg",
            """
if [[ "$*" == "-r -t get_tree" ]]; then
    printf '%s\n' \
      '{"focused":false,"nodes":[{"focused":true,"id":42,"pid":48123,"app_id":"looking-glass","name":"guest controlled title"}]}'
    exit 0
fi

exit 0
""",
        )

        write_fake_command(
            bin_dir / "hyprctl",
            """
if [[ "${1:-}" == "activewindow" &&
      "${2:-}" == "-j" ]]
then
    printf '%s\n' \
      '{"address":"0xabc","pid":48123,"class":"looking-glass","title":"guest controlled title"}'
    exit 0
fi

exit 0
""",
        )

        sway = run_adapter(
            backend="sway",
            operation="focused-window-json",
            bin_dir=bin_dir,
        )

        require(
            sway.returncode == 0,
            (
                "Sway focused-window-json failed: "
                + sway.stderr
            ),
        )

        sway_payload = json.loads(
            sway.stdout
        )

        require(
            sway_payload == {
                "app_id": "looking-glass",
                "pid": 48123,
                "title": "guest controlled title",
                "window_id": "42",
            },
            "Sway PID-bearing snapshot changed",
        )

        hypr = run_adapter(
            backend="hyprland",
            operation="focused-window-json",
            bin_dir=bin_dir,
        )

        require(
            hypr.returncode == 0,
            (
                "Hyprland focused-window-json failed: "
                + hypr.stderr
            ),
        )

        hypr_payload = json.loads(
            hypr.stdout
        )

        require(
            hypr_payload == {
                "app_id": "looking-glass",
                "pid": 48123,
                "title": "guest controlled title",
                "window_id": "0xabc",
            },
            "Hyprland PID-bearing snapshot changed",
        )

        # Existing API is deliberately preserved.
        sway_legacy = run_adapter(
            backend="sway",
            operation="focused-window",
            bin_dir=bin_dir,
        )

        require(
            sway_legacy.returncode == 0,
            "legacy Sway focused-window failed",
        )

        require(
            sway_legacy.stdout
            == "42\tlooking-glass\n",
            "legacy Sway focused-window shape changed",
        )

        hypr_legacy = run_adapter(
            backend="hyprland",
            operation="focused-window",
            bin_dir=bin_dir,
        )

        require(
            hypr_legacy.returncode == 0,
            "legacy Hyprland focused-window failed",
        )

        require(
            hypr_legacy.stdout
            == "0xabc\tlooking-glass\n",
            "legacy Hyprland focused-window shape changed",
        )


def main() -> int:
    require(
        OPEN.is_file(),
        "launcher source missing",
    )

    require(
        ADAPTER.is_file(),
        "compositor adapter missing",
    )

    verify_launcher_source()
    verify_registry()
    verify_compositor_snapshot()

    print(
        "HyperLab launcher/compositor provenance binding contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
