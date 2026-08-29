#!/usr/bin/env python3
"""Contract for the hardware-proven Looking Glass captured-input compatibility patch."""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATCH_REL = Path("roles/looking_glass/files/client-captured-button-press.patch")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Looking Glass client input contract: {message}")


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    defaults = yaml.safe_load(text("roles/looking_glass/defaults/main.yml"))
    tasks = text("roles/looking_glass/tasks/main.yml")
    opener = text("tools/hyperlabctl/hyperlabctl/commands/open.py")
    patch_path = ROOT / PATCH_REL
    patch = patch_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()

    require(
        defaults["looking_glass_input_patch"] == PATCH_REL.name,
        "role must name the reviewed client input patch",
    )
    require(
        defaults["looking_glass_input_patch_target"] == "client/src/app.c",
        "client input patch target changed",
    )
    require(
        defaults["looking_glass_input_patch_sha256"] == digest,
        "client input patch SHA-256 differs from the managed bytes",
    )
    require(
        "if (!core_inputEnabled() || (!g_cursor.grab && !g_cursor.inView))" in patch,
        "captured mouse presses are not accepted while the client remains grabbed",
    )
    require(
        "if (!core_inputEnabled() || !g_cursor.inView)" in patch,
        "patch no longer proves the exact upstream press gate it replaces",
    )
    require(
        "DEBUG_" not in patch and "DIAG" not in patch,
        "production patch still contains diagnostic logging",
    )
    for marker in (
        "looking_glass_stamp_data.input_patch_sha256",
        "looking_glass_input_patch_sha256",
        "looking_glass_input_patch_target",
        "apply\n              - --check",
        "checkout\n              - --",
        "input_patch_sha256: {{ looking_glass_input_patch_sha256 }}",
    ):
        require(marker in tasks, f"managed patch lifecycle missing: {marker}")

    require(
        '"app:shmFile=/dev/kvmfr0"' in opener,
        "Looking Glass launcher must pass the valid B7 shared-memory option",
    )
    require(
        '["looking-glass-client", "-F", "/dev/kvmfr0"]' not in opener,
        "Looking Glass launcher still passes kvmfr0 as an invalid positional argument",
    )

    print("Looking Glass client input contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
