#!/usr/bin/env python3
"""Host-independent mutation tests for M3 image-store path safety."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools/guest_store_guard.py"
LAYOUT_DIRECTORIES = [
    "",
    "bases",
    "bases/windows",
    "bases/linux",
    "disposable",
    "permanent",
    "cloud-init",
    "nvram",
    "tpm",
    "snapshots",
    "exports",
    "cache",
    "state",
]
MANAGEMENT_DIRECTORIES = ["state/vms", "state/domains", "state/locks"]


def run(store: Path, require_roots: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--layout",
            str(store / "state/layout.yml"),
            "--store",
            str(store),
            "--require-management-roots",
            "true" if require_roots else "false",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def build_store(root: Path) -> Path:
    store = root / "store"
    for relative in LAYOUT_DIRECTORIES + MANAGEMENT_DIRECTORIES:
        (store if relative == "" else store / relative).mkdir(parents=True, exist_ok=True)
    layout = {
        "root": str(store),
        "filesystem": str(root),
        "fstype": "fixture",
        "administered_by": "root:root",
        "qemu_identity": "qemu:qemu",
        "swtpm_identity": "swtpm:swtpm",
        "directories": LAYOUT_DIRECTORIES,
    }
    (store / "state/layout.yml").write_text(
        yaml.safe_dump(layout, sort_keys=False), encoding="utf-8"
    )
    return store


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        store = build_store(root)

        accepted = run(store, True)
        assert accepted.returncode == 0, accepted.stderr

        (store / "state/locks").rmdir()
        create_preflight = run(store, False)
        assert create_preflight.returncode == 0, create_preflight.stderr
        required = run(store, True)
        assert required.returncode == 2 and "management directory is missing" in required.stderr
        (store / "state/locks").mkdir()

        outside = root / "outside"
        outside.mkdir()
        (store / "disposable").rmdir()
        (store / "disposable").symlink_to(outside, target_is_directory=True)
        redirected = run(store, True)
        assert redirected.returncode == 2 and "not a real directory" in redirected.stderr

    print("guest store guard contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
