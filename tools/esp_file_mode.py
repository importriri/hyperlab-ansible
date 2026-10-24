#!/usr/bin/env python3
"""Decide the mode a file written on the ESP will read
(problems/vfio-boot-modes-on-vfat-esp.md).

stdin is a JSON list of `findmnt -J -T DIR -o TARGET,FSTYPE,OPTIONS`
documents, one per directory a role writes into; they must all describe
the same filesystem. On vfat a file's mode comes from the mount, and chmod
cannot change it: 0777 without the fmask bits, and without the execute
bits under showexec (a .conf file is not an executable name). The one
exception is the DOS read-only attribute: such a file reads without its
write bits, and the first chmod to the mode below clears the attribute, so
the first apply changes it once and the next ones do not. On a filesystem
that keeps modes, the answer is --wanted. Anything else, a mount that lets
anyone but root write the file or create one in its directory (dmask), or
a file not owned by root, is a refusal.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

MODE_PATTERN = re.compile(r"^0[0-7]{3}$")
MASK_PATTERN = re.compile(r"^[0-7]{1,4}$")
KEEPS_MODES = frozenset({"ext2", "ext3", "ext4", "btrfs", "xfs"})
GROUP_OR_OTHER_WRITE = 0o022
EXECUTE = 0o111


class ModeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModeError(message)


def filesystem(document: Any) -> tuple[str, str, str]:
    require(isinstance(document, str), "every findmnt document must be a string")
    try:
        payload = json.loads(document)
    except json.JSONDecodeError as exc:
        raise ModeError(f"a findmnt document is not valid JSON: {exc}") from exc
    require(isinstance(payload, dict), "a findmnt document must be a mapping")
    found = payload.get("filesystems")
    require(isinstance(found, list) and len(found) == 1,
            "a findmnt document must describe exactly one mounted filesystem")
    entry = found[0]
    require(isinstance(entry, dict), "a findmnt filesystem entry must be a mapping")
    target, fstype, options = entry.get("target"), entry.get("fstype"), entry.get("options")
    require(isinstance(target, str) and target.startswith("/"), "the mount target must be an absolute path")
    require(isinstance(fstype, str) and fstype != "", "the mount must name its filesystem type")
    require(isinstance(options, str), "the mount options must be a string")
    return target, fstype, options


def parse_options(options: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for option in options.split(","):
        key, _, value = option.partition("=")
        parsed.setdefault(key, []).append(value)
    return parsed


def single(parsed: dict[str, list[str]], key: str) -> str | None:
    values = parsed.get(key, [])
    require(len(values) <= 1, f"the vfat mount repeats {key}")
    return values[0] if values else None


def mask(parsed: dict[str, list[str]], key: str) -> int:
    value = single(parsed, key)
    require(value is not None, f"the vfat mount does not show its {key}")
    require(MASK_PATTERN.fullmatch(value) is not None and int(value, 8) <= 0o777,
            f"the vfat {key} is not an octal permission mask: {value}")
    return int(value, 8)


def vfat_mode(options: str) -> int:
    parsed = parse_options(options)
    fmask = mask(parsed, "fmask")
    directories = 0o777 & ~mask(parsed, "dmask")
    require(directories & GROUP_OR_OTHER_WRITE == 0,
            f"directories there would read {directories:04o}: a user other than root "
            "could create or replace a boot entry")
    for owner in ("uid", "gid"):
        value = single(parsed, owner)
        require(value in (None, "0"), f"vfat files there belong to {owner} {value}, not root")
    mode = 0o777 & ~fmask
    if "showexec" in parsed:
        single(parsed, "showexec")
        mode &= ~EXECUTE
    return mode


def decide(documents: Any, wanted: int) -> int:
    require(isinstance(documents, list) and documents, "stdin must be a non-empty JSON list")
    mounts = {filesystem(document) for document in documents}
    require(len(mounts) == 1, "the directories are not on one filesystem with one set of options")
    _, fstype, options = mounts.pop()
    if fstype == "vfat":
        mode = vfat_mode(options)
    else:
        require(fstype in KEEPS_MODES, f"cannot tell the mode a file on {fstype} keeps")
        mode = wanted
    require(mode & GROUP_OR_OTHER_WRITE == 0,
            f"files there would read {mode:04o}: a user other than root could write them")
    return mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wanted", required=True,
                        help="the mode, 0NNN, on a filesystem that keeps modes")
    args = parser.parse_args(argv)
    try:
        require(MODE_PATTERN.fullmatch(args.wanted) is not None,
                f"--wanted must be a mode such as 0644: {args.wanted}")
        require(int(args.wanted, 8) & GROUP_OR_OTHER_WRITE == 0,
                f"--wanted {args.wanted} lets a user other than root write")
        try:
            documents = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise ModeError(f"stdin is not valid JSON: {exc}") from exc
        mode = decide(documents, int(args.wanted, 8))
    except ModeError as exc:
        print(f"esp_file_mode: {exc}", file=sys.stderr)
        return 2
    print(f"{mode:04o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
