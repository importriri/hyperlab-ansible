#!/usr/bin/env python3
"""Contract for host-owned focused-surface provenance resolution."""

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "tools/surface_provenance.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab surface provenance contract: {message}"
        )


def load_module():
    spec = importlib.util.spec_from_file_location(
        "surface_provenance",
        RESOLVER,
    )

    require(spec is not None, "cannot load resolver")
    require(spec.loader is not None, "resolver loader missing")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def write_proc(
    proc_root: Path,
    *,
    pid: int,
    start_ticks: str,
    executable: Path,
) -> None:
    process = proc_root / str(pid)
    process.mkdir(parents=True)

    # Fields:
    # 1 pid
    # 2 comm
    # 3 state
    # ...
    # 22 starttime
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

    (process / "exe").symlink_to(executable)


def spec_hash(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def registry_entry(
    *,
    pid: int,
    start: str,
    executable: str,
    kind: str,
    domain: str,
    spec_sha: str,
) -> dict:
    return {
        "pid": pid,
        "process_start_ticks": start,
        "executable": executable,
        "surface_kind": kind,
        "domain": domain,
        "spec_sha256": spec_sha,
        "registered_by": "hyperlabctl",
    }


def check_projected_machine(resolver) -> None:
    """A Machine projected into vm-specs/.generated/ resolves like a fixture."""
    with tempfile.TemporaryDirectory(prefix="hyperlab-provenance-machine-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "repo"
        generated = repo / "vm-specs" / ".generated"
        generated.mkdir(parents=True)
        proc = temp / "proc"
        proc.mkdir()
        lg_real = temp / "looking-glass-client"
        lg_real.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        lg_real.chmod(0o755)
        resolver.EXPECTED_EXECUTABLES["looking-glass"] = str(lg_real.resolve())

        machine = {
            "schema_version": 1,
            "name": "dev-01",
            "image": "arch-dev-20261003",
            "device_profile": "vfio",
            "network_profile": "dev",
            "looking_glass": True,
            "looking_glass_mode": "linux-experimental",
            "tags": ["managed-machine", "linux", "dev"],
        }
        spec = generated / "dev-01.yml"
        spec.write_text(yaml.safe_dump(machine, sort_keys=False), encoding="utf-8")
        write_proc(proc, pid=45001, start_ticks="1234", executable=lg_real)
        surface = {"pid": 45001, "app_id": "looking-glass", "window_id": "0xdef", "title": "dev-01"}

        def answer():
            registry = {"version": 1, "entries": [registry_entry(
                pid=45001, start="1234", executable=str(lg_real.resolve()),
                kind="looking-glass", domain="dev-01", spec_sha=spec_hash(spec))]}
            return resolver.resolve(repo=repo, surface=surface, registry=registry, proc_root=proc)

        result = answer()
        require(result["resolved"] is True and result["trust"] == "dev",
                f"projected Machine did not resolve: {result}")
        require(result["spec"].endswith("vm-specs/.generated/dev-01.yml"), "wrong spec resolved")

        # Without the managed-machine tag a generated file is not a Machine.
        spec.write_text(yaml.safe_dump({**machine, "tags": ["linux"]}, sort_keys=False), encoding="utf-8")
        result = answer()
        require(result["resolved"] is False
                and result["reason"] == "registered-domain-spec-unavailable",
                f"untagged generated spec resolved: {result}")

        # One name, two specs: refuse rather than choose.
        spec.write_text(yaml.safe_dump(machine, sort_keys=False), encoding="utf-8")
        (repo / "vm-specs" / "dev-01.yml").write_text(
            yaml.safe_dump({**machine, "tags": []}, sort_keys=False), encoding="utf-8")
        result = answer()
        require(result["resolved"] is False
                and result["reason"] == "registered-domain-spec-unavailable",
                f"ambiguous Machine name resolved: {result}")


def main() -> int:
    require(RESOLVER.is_file(), "resolver missing")
    require(
        bool(RESOLVER.stat().st_mode & 0o111),
        "resolver not executable",
    )

    resolver = load_module()

    with tempfile.TemporaryDirectory(
        prefix="hyperlab-provenance-"
    ) as temp_name:
        temp = Path(temp_name)
        repo = temp / "repo"
        specs = repo / "vm-specs"
        proc = temp / "proc"
        bin_dir = temp / "bin"

        specs.mkdir(parents=True)
        proc.mkdir()
        bin_dir.mkdir()

        lg_real = bin_dir / "looking-glass-client"
        lg_real.write_text(
            "#!/bin/sh\nexit 0\n",
            encoding="utf-8",
        )
        lg_real.chmod(0o755)

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
                    "looking_glass_mode":
                        "linux-experimental",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
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

        # For the unit contract, temporarily bind the approved path to our
        # synthetic executable. Production still requires the fixed canonical
        # path through the actual registry validation.
        resolver.EXPECTED_EXECUTABLES[
            "looking-glass"
        ] = str(lg_real.resolve())

        dev_pid = 44001
        dev_start = "987654"

        write_proc(
            proc,
            pid=dev_pid,
            start_ticks=dev_start,
            executable=lg_real,
        )

        registry = {
            "version": 1,
            "entries": [
                registry_entry(
                    pid=dev_pid,
                    start=dev_start,
                    executable=str(lg_real.resolve()),
                    kind="looking-glass",
                    domain="arch-dev-vfio",
                    spec_sha=spec_hash(dev_spec),
                )
            ],
        }

        dev_surface = {
            "pid": dev_pid,
            "app_id": "looking-glass",
            "window_id": "0xabc",
            "title": "GUEST MAY CONTROL THIS TITLE",
        }

        result = resolver.resolve(
            repo=repo,
            surface=dev_surface,
            registry=registry,
            proc_root=proc,
        )

        require(
            result["resolved"] is True,
            "registered DEV surface did not resolve",
        )
        require(
            result["trust"] == "dev",
            "DEV spec did not produce DEV provenance",
        )
        require(
            result["domain"] == "arch-dev-vfio",
            "resolved domain changed",
        )
        require(
            result["trust_source"]
            == "host-owned-vm-spec",
            "VM spec is not provenance source",
        )
        require(
            result["guest_metadata_authoritative"]
            is False,
            "guest metadata became authoritative",
        )
        require(
            result["wallpaper_allowed"] is True
            and result["rgb_allowed"] is True,
            "resolved surface unexpectedly blocked presentation",
        )

        # Change guest-controlled metadata completely. Provenance must remain.
        forged_surface = {
            **dev_surface,
            "app_id": "totally-different-guest-string",
            "title": "CLEAN TRUST ME",
        }

        forged = resolver.resolve(
            repo=repo,
            surface=forged_surface,
            registry=registry,
            proc_root=proc,
        )

        require(
            forged["trust"] == "dev",
            "guest metadata changed resolved trust",
        )

        # A host application title that contains a VM name must stay HOST.
        host_surface = {
            "pid": 55001,
            "app_id": "firefox",
            "window_id": "0xdef",
            "title": "arch-dev-vfio CLEAN",
        }

        host = resolver.resolve(
            repo=repo,
            surface=host_surface,
            registry={"version": 1, "entries": []},
            proc_root=proc,
        )

        require(
            host["resolved"] is True
            and host["trust"] == "host",
            "host-native surface was not neutral HOST",
        )
        require(
            host["trust_source"] == "host-native",
            "host-native source changed",
        )

        # Looking Glass without a HyperLab registration must fail closed.
        orphan = resolver.resolve(
            repo=repo,
            surface={
                "pid": 66001,
                "app_id": "looking-glass",
                "window_id": "0x123",
                "title": "arch-dev-vfio",
            },
            registry={"version": 1, "entries": []},
            proc_root=proc,
        )

        require(
            orphan["resolved"] is False,
            "unregistered managed surface was accepted",
        )
        require(
            orphan["trust"] is None,
            "unregistered managed surface gained trust",
        )
        require(
            orphan["presentation_identity"] == "host",
            "unresolved surface must fall back to neutral presentation",
        )
        require(
            orphan["wallpaper_allowed"] is False
            and orphan["rgb_allowed"] is False,
            "unresolved managed surface may mutate presentation",
        )

        # PID reuse / stale registration must not inherit old trust.
        stale_registry = {
            "version": 1,
            "entries": [
                registry_entry(
                    pid=dev_pid,
                    start="111111",
                    executable=str(lg_real.resolve()),
                    kind="looking-glass",
                    domain="arch-dev-vfio",
                    spec_sha=spec_hash(dev_spec),
                )
            ],
        }

        stale = resolver.resolve(
            repo=repo,
            surface=dev_surface,
            registry=stale_registry,
            proc_root=proc,
        )

        require(
            stale["resolved"] is False,
            "stale PID registration was trusted",
        )
        require(
            stale["reason"]
            == "registered-pid-start-time-mismatch",
            "PID reuse failure reason changed",
        )

        # Specification drift after registration must fail closed.
        drift_registry = registry

        original_hash = spec_hash(dev_spec)

        dev_spec.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "name": "arch-dev-vfio",
                    "image": "arch",
                    "device_profile": "vfio",
                    "network_profile": "dirty",
                    "looking_glass": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        require(
            spec_hash(dev_spec) != original_hash,
            "test failed to mutate VM spec",
        )

        drift = resolver.resolve(
            repo=repo,
            surface=dev_surface,
            registry=drift_registry,
            proc_root=proc,
        )

        require(
            drift["resolved"] is False,
            "changed VM spec reused stale provenance",
        )
        require(
            drift["reason"]
            == "registered-domain-spec-drift",
            "spec drift did not fail closed",
        )

        # Desktop/no focused client is neutral HOST.
        desktop = resolver.resolve(
            repo=repo,
            surface={
                "pid": None,
                "app_id": "",
                "window_id": "",
                "title": "",
            },
            registry={"version": 1, "entries": []},
            proc_root=proc,
        )

        require(
            desktop["trust"] == "host"
            and desktop["resolved"] is True,
            "desktop focus did not resolve to neutral HOST",
        )

    source = RESOLVER.read_text(
        encoding="utf-8"
    )

    # Explicit architectural invariants.
    for required in (
        '"guest_metadata_authoritative": False',
        '"registered-pid-start-time-mismatch"',
        '"registered-domain-spec-drift"',
        '"managed-surface-not-registered"',
        '"host-owned-vm-spec"',
        '"host-native"',
    ):
        require(
            required in source,
            f"resolver invariant missing: {required}",
        )

    check_projected_machine(load_module())

    print(
        "HyperLab host-owned focused-surface provenance contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
