#!/usr/bin/env python3
"""Read one managed guest's SSH host key through QEMU Guest Agent.

The key travels over the hypervisor's own virtio channel, not over the guest
network, so the first SSH connection never trusts a key it was shown on the
wire. The output is one known_hosts line for the given address.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys


DOMAIN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
KEY_PATTERN = re.compile(r"^ssh-ed25519 (AAAAC3NzaC1lZDI1NTE5[A-Za-z0-9+/]+={0,2})(?: \S.*)?$")
HOST_KEY_PATH = "/etc/ssh/ssh_host_ed25519_key.pub"
LIBVIRT_URI = "qemu:///system"
MAX_KEY_BYTES = 4096


def agent_argv(virsh_bin: Path, domain: str, command: dict) -> list[str]:
    return [str(virsh_bin), "-c", LIBVIRT_URI, "qemu-agent-command", domain, json.dumps(command)]


def known_hosts_line(address: str, public_key: str) -> str:
    """Validate an ed25519 public key file and pin it to one guest address."""
    ip = ipaddress.ip_address(address)
    lines = [line.strip() for line in public_key.strip().splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("the guest host key file must hold exactly one key")
    match = KEY_PATTERN.fullmatch(lines[0])
    if match is None:
        raise ValueError("the guest host key is not an ed25519 public key")
    try:
        blob = base64.b64decode(match.group(1), validate=True)
    except binascii.Error as exc:
        raise ValueError("the guest host key is not valid base64") from exc
    # string "ssh-ed25519" (4 + 11 bytes) then a 32-byte key (4 + 32 bytes)
    if len(blob) != 51 or blob[4:15] != b"ssh-ed25519" or blob[15:19] != b"\x00\x00\x00\x20":
        raise ValueError("the guest host key has the wrong ed25519 shape")
    return f"{ip} ssh-ed25519 {match.group(1)}"


def read_guest_file(run, virsh_bin: Path, domain: str, path: str) -> str:
    def call(command: dict) -> dict:
        result = run(agent_argv(virsh_bin, domain, command))
        reply = json.loads(result)
        if not isinstance(reply, dict) or "return" not in reply:
            raise ValueError("QEMU Guest Agent returned no result")
        return reply["return"]

    handle = call({"execute": "guest-file-open", "arguments": {"path": path, "mode": "r"}})
    if not isinstance(handle, int):
        raise ValueError("QEMU Guest Agent returned no file handle")
    try:
        data = call({"execute": "guest-file-read", "arguments": {"handle": handle, "count": MAX_KEY_BYTES}})
    finally:
        call({"execute": "guest-file-close", "arguments": {"handle": handle}})
    if not isinstance(data, dict) or not isinstance(data.get("buf-b64"), str):
        raise ValueError("QEMU Guest Agent returned no file content")
    if data.get("eof") is not True:
        raise ValueError("the guest host key file is unexpectedly large")
    return base64.b64decode(data["buf-b64"], validate=True).decode("ascii")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--virsh-bin", type=Path, default=Path("/usr/bin/virsh"))
    parser.add_argument("--domain", required=True)
    parser.add_argument("--address", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not DOMAIN_PATTERN.fullmatch(args.domain):
        print("managed domain name is malformed", file=sys.stderr)
        return 2
    if not args.virsh_bin.is_absolute():
        print("virsh path must be absolute", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["LC_ALL"] = "C"

    def run(argv: list[str]) -> str:
        return subprocess.run(argv, check=True, capture_output=True, text=True,
                              timeout=20, env=environment).stdout

    try:
        line = known_hosts_line(args.address, read_guest_file(run, args.virsh_bin, args.domain, HOST_KEY_PATH))
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
