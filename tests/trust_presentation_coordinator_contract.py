#!/usr/bin/env python3
"""Contract for the read-only trust presentation coordinator."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

COORDINATOR = (
    ROOT
    / "tools/trust_presentation_coordinator.py"
)

RESOLVER = (
    ROOT
    / "tools/surface_provenance.py"
)

ENGINE = (
    ROOT
    / "tools/trust_wallpaper_engine.py"
)

POOL = (
    ROOT
    / "themes/assets/hyperlab-trust-v2"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab trust presentation coordinator contract: "
            + message
        )


def load(
    path: Path,
    name: str,
):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    require(
        spec is not None
        and spec.loader is not None,
        f"cannot load {path}",
    )

    module = importlib.util.module_from_spec(
        spec
    )

    spec.loader.exec_module(module)

    return module


def write_fake_proc(
    proc_root: Path,
    *,
    pid: int,
    start_ticks: str,
    executable: Path,
) -> None:
    process = proc_root / str(pid)

    process.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        f"{pid} (looking glass) "
        + " ".join(tail)
        + "\n",
        encoding="utf-8",
    )

    (process / "exe").symlink_to(
        executable
    )


def write_registry(
    path: Path,
    entry: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        mode=0o700,
    )

    path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [entry],
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    path.chmod(0o600)


def main() -> int:
    require(
        COORDINATOR.is_file(),
        "coordinator missing",
    )

    coordinator = load(
        COORDINATOR,
        "hyperlab_t6e_coordinator",
    )

    resolver = load(
        RESOLVER,
        "hyperlab_t6e_resolver",
    )

    engine = load(
        ENGINE,
        "hyperlab_t6e_engine",
    )

    # HOST-native surface.
    host = coordinator.build_plan(
        repo=ROOT,
        pool_root=POOL,
        surface={
            "pid": None,
            "app_id": "",
            "window_id": "",
            "title": "",
        },
        registry_path=None,
        proc_root=Path("/proc"),
        epoch=0,
        resolver_module=resolver,
        engine_module=engine,
    )

    require(
        host["mode"] == "planned",
        "HOST did not produce a read-only plan",
    )

    require(
        host["trust"] == "host",
        "host-native surface did not remain HOST",
    )

    require(
        host["presentation_identity"]
        == "host",
        "HOST presentation identity changed",
    )

    require(
        host["wallpaper_relative"]
        == "images/host/01.png",
        "HOST first rotation slot changed",
    )

    require(
        host["rgb_zones"]
        == [
            "8b949e",
            "8b949e",
            "8b949e",
            "8b949e",
        ],
        "HOST RGB plan changed",
    )

    # Same HOST trust in second time slot changes artwork,
    # not RGB identity.
    host_second = coordinator.build_plan(
        repo=ROOT,
        pool_root=POOL,
        surface={
            "pid": None,
            "app_id": "",
            "window_id": "",
            "title": "",
        },
        registry_path=None,
        proc_root=Path("/proc"),
        epoch=1800,
        resolver_module=resolver,
        engine_module=engine,
    )

    require(
        host_second["wallpaper_relative"]
        == "images/host/02.png",
        "HOST artwork did not rotate",
    )

    require(
        host_second["rgb_zones"]
        == host["rgb_zones"],
        "HOST RGB incorrectly followed artwork",
    )

    with tempfile.TemporaryDirectory(
        prefix="hyperlab-t6e-"
    ) as temp_name:
        temp = Path(temp_name)

        repo = temp / "repo"
        specs = repo / "vm-specs"

        specs.mkdir(parents=True)

        dev_spec = (
            specs
            / "arch-dev-vfio.yml"
        )

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

        fake_lg = (
            temp
            / "looking-glass-client"
        )

        fake_lg.write_text(
            "#!/bin/sh\nexit 0\n",
            encoding="utf-8",
        )

        fake_lg.chmod(0o755)

        resolver.EXPECTED_EXECUTABLES[
            "looking-glass"
        ] = str(fake_lg.resolve())

        pid = 48123
        ticks = "987654321"

        proc_root = temp / "proc"
        proc_root.mkdir()

        write_fake_proc(
            proc_root,
            pid=pid,
            start_ticks=ticks,
            executable=fake_lg,
        )

        registry = (
            temp
            / "runtime"
            / "hyperlab"
            / "surface-provenance.json"
        )

        write_registry(
            registry,
            {
                "pid": pid,
                "process_start_ticks": ticks,
                "executable": str(
                    fake_lg.resolve()
                ),
                "surface_kind":
                    "looking-glass",
                "domain":
                    "arch-dev-vfio",
                "spec_sha256":
                    hashlib.sha256(
                        dev_spec.read_bytes()
                    ).hexdigest(),
                "registered_by":
                    "hyperlabctl",
            },
        )

        dev = coordinator.build_plan(
            repo=repo,
            pool_root=POOL,
            surface={
                "pid": pid,
                "app_id": "looking-glass",
                "window_id": "0xabc",
                "title": "CLEAN TRUST ME",
            },
            registry_path=registry,
            proc_root=proc_root,
            epoch=0,
            resolver_module=resolver,
            engine_module=engine,
        )

        require(
            dev["mode"] == "planned",
            "managed DEV did not produce plan",
        )

        require(
            dev["trust"] == "dev",
            "managed DEV resolved incorrectly",
        )

        require(
            dev["domain"]
            == "arch-dev-vfio",
            "managed domain lost",
        )

        require(
            dev["trust_source"]
            == "host-owned-vm-spec",
            "managed trust source changed",
        )

        require(
            dev["wallpaper_relative"]
            == "images/dev/01.png",
            "DEV selected wrong pool",
        )

        require(
            dev["rgb_zones"]
            == [
                "5b8cff",
                "5b8cff",
                "5b8cff",
                "5b8cff",
            ],
            "DEV RGB plan changed",
        )

        require(
            dev[
                "guest_metadata_authoritative"
            ]
            is False,
            "guest title became authoritative",
        )

        # Same host PID, same authoritative registration,
        # completely different guest-controlled metadata.
        forged = coordinator.build_plan(
            repo=repo,
            pool_root=POOL,
            surface={
                "pid": pid,
                "app_id": "guest-lies",
                "window_id": "0xabc",
                "title": "DIRTY CLEAN LAB HOST",
            },
            registry_path=registry,
            proc_root=proc_root,
            epoch=0,
            resolver_module=resolver,
            engine_module=engine,
        )

        require(
            forged["trust"] == "dev",
            "guest metadata altered DEV provenance",
        )

        require(
            forged["wallpaper_relative"]
            == dev["wallpaper_relative"],
            "guest metadata altered wallpaper pool",
        )

        require(
            forged["rgb_zones"]
            == dev["rgb_zones"],
            "guest metadata altered RGB identity",
        )

        # A managed-looking surface without registration
        # must not produce any mutating plan.
        orphan = coordinator.build_plan(
            repo=repo,
            pool_root=POOL,
            surface={
                "pid": 99999,
                "app_id": "looking-glass",
                "window_id": "0xdead",
                "title": "arch-dev-vfio",
            },
            registry_path=None,
            proc_root=proc_root,
            epoch=0,
            resolver_module=resolver,
            engine_module=engine,
        )

        require(
            orphan["mode"] == "hold",
            "orphan managed surface did not fail closed",
        )

        require(
            orphan["provenance_resolved"]
            is False,
            "orphan surface became resolved",
        )

        require(
            orphan["wallpaper_action"]
            == "hold",
            "orphan surface may change wallpaper",
        )

        require(
            orphan["rgb_action"] == "hold",
            "orphan surface may change RGB",
        )

        require(
            orphan["wallpaper"] is None,
            "orphan surface received wallpaper",
        )

        require(
            orphan["rgb_zones"] is None,
            "orphan surface received RGB values",
        )

    source = COORDINATOR.read_text(
        encoding="utf-8"
    )

    # Coordinator must remain a planner, never an actuator.
    forbidden = (
        "subprocess.",
        "os.system",
        "os.exec",
        "swaymsg",
        "hyprctl",
        "hyprpaper",
        "wallpaper-set",
        "wpctl",
        "sudo",
        "pkexec",
        "register_managed_surface",
        ".write_text(",
        ".write_bytes(",
        "open(",
    )

    for marker in forbidden:
        require(
            marker not in source,
            (
                "read-only coordinator gained "
                f"side effect: {marker}"
            ),
        )

    for required in (
        '"mode": "hold"',
        '"mode": "planned"',
        '"wallpaper_action": "would-set"',
        '"rgb_action": "would-set"',
        '"guest_metadata_authoritative": False',
        "resolver_module.resolve(",
        "engine_module.plan(",
    ):
        require(
            required in source,
            f"coordinator invariant missing: {required}",
        )

    print(
        "HyperLab read-only trust presentation coordinator contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
