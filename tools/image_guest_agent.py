#!/usr/bin/env python3
"""Look inside one Linux qcow2, read-only, for the QEMU Guest Agent.

A manifest that claims `supports.qemu_guest_agent` is a promise HyperLab
relies on: a new Machine's SSH host key is read through the agent. This tool
checks the promise against the image itself before it is sealed or used. It
opens the image with libguestfs in read-only mode and never boots it.

The answer is one JSON object: whether the agent binary and its systemd unit
are present, and where.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BINARIES = ("/usr/bin/qemu-ga", "/usr/sbin/qemu-ga")
UNITS = (
    "/usr/lib/systemd/system/qemu-guest-agent.service",
    "/lib/systemd/system/qemu-guest-agent.service",
)
CANDIDATES = BINARIES + UNITS
TIMEOUT_SECONDS = 300


def script() -> str:
    return "".join(f"is-file-opts {path} followsymlinks:true\n" for path in CANDIDATES)


def evaluate(output: str) -> dict:
    """Map guestfish's one true/false line per candidate to the answer."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != len(CANDIDATES) or any(line not in ("true", "false") for line in lines):
        raise ValueError("guestfish did not answer every check")
    found = {path for path, line in zip(CANDIDATES, lines) if line == "true"}
    binary = next((path for path in BINARIES if path in found), None)
    unit = next((path for path in UNITS if path in found), None)
    return {"qemu_guest_agent": binary is not None and unit is not None,
            "binary": binary, "unit": unit}


def inspect(image: Path, guestfish: str, run=subprocess.run) -> dict:
    env = dict(os.environ, LIBGUESTFS_BACKEND="direct")
    result = run([guestfish, "--ro", "--format=qcow2", "-a", str(image), "-i"],
                 input=script(), capture_output=True, text=True, env=env,
                 timeout=TIMEOUT_SECONDS, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ValueError("guestfish could not open the image: "
                         + (detail[-1] if detail else f"exit {result.returncode}"))
    return evaluate(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--guestfish", default="/usr/bin/guestfish")
    args = parser.parse_args()
    if not args.image.is_absolute() or args.image.is_symlink() or not args.image.is_file():
        print("the image must be an absolute path to a regular file", file=sys.stderr)
        return 2
    try:
        answer = inspect(args.image, args.guestfish)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"image": str(args.image), **answer}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
