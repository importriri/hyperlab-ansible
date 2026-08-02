#!/usr/bin/env python3
"""Prepare a libvirt network definition while preserving its identity."""
from __future__ import annotations

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def read_text(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def network_name(root: ET.Element) -> str:
    return (root.findtext("name") or "").strip()


def insert_after(root: ET.Element, anchor_tag: str, element: ET.Element) -> None:
    children = list(root)
    for index, child in enumerate(children):
        if child.tag == anchor_tag:
            root.insert(index + 1, element)
            return
    root.insert(0, element)


def preserve_identity(desired_text: str, current_text: str) -> str:
    desired = ET.fromstring(desired_text)
    if desired.tag != "network":
        raise ValueError("desired XML root must be <network>")

    desired_name = network_name(desired)
    if not desired_name:
        raise ValueError("desired network name is empty")

    if not current_text.strip():
        return ET.tostring(desired, encoding="unicode") + "\n"

    current = ET.fromstring(current_text)
    if current.tag != "network":
        raise ValueError("current XML root must be <network>")

    current_name = network_name(current)
    if current_name != desired_name:
        raise ValueError(
            f"network name mismatch: desired={desired_name!r} current={current_name!r}"
        )

    current_uuid = (current.findtext("uuid") or "").strip()
    if not current_uuid:
        raise ValueError(f"current network {current_name!r} has no UUID")

    desired_uuid = desired.find("uuid")
    if desired_uuid is None:
        desired_uuid = ET.Element("uuid")
        desired_uuid.text = current_uuid
        insert_after(desired, "name", desired_uuid)
    elif (desired_uuid.text or "").strip() != current_uuid:
        raise ValueError(f"desired network {desired_name!r} changes the existing UUID")

    current_mac = current.find("mac")
    desired_mac = desired.find("mac")
    if current_mac is not None:
        current_address = current_mac.get("address", "").strip().lower()
        if desired_mac is None:
            copied_mac = ET.Element("mac", dict(current_mac.attrib))
            insert_after(desired, "bridge", copied_mac)
        elif desired_mac.get("address", "").strip().lower() != current_address:
            raise ValueError(f"desired network {desired_name!r} changes the existing MAC")

    return ET.tostring(desired, encoding="unicode") + "\n"


def atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"usage: {sys.argv[0]} DESIRED CURRENT|- OUTPUT",
            file=sys.stderr,
        )
        return 2

    try:
        prepared = preserve_identity(read_text(sys.argv[1]), read_text(sys.argv[2]))
        atomic_write(Path(sys.argv[3]), prepared)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
