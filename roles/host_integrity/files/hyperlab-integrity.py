#!/usr/bin/python3
"""hyperlab-integrity - file integrity of HyperLab's trust points (ADR 0040).

Arch ships no AIDE, so HyperLab keeps this small, reviewable checker. It
records the SHA-256, owner, group and mode of every regular file and symlink
target under the configured paths, and reports what was added, removed or
changed since. It detects; it does not prevent: root can rewrite the
baseline, so a report counts once it has left the host.

    hyperlab-integrity baseline   record the current state (root)
    hyperlab-integrity check      compare; exit 1 on any difference
    hyperlab-integrity accept     record again after a reviewed change

Configuration: /etc/hyperlab/integrity.json  {"paths": ["/etc/sudoers", ...]}
Baseline:      /var/lib/hyperlab-integrity/baseline.json (root, 0600)
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("HYPERLAB_INTEGRITY_CONFIG", "/etc/hyperlab/integrity.json"))
STATE = Path(os.environ.get("HYPERLAB_INTEGRITY_STATE", "/var/lib/hyperlab-integrity"))
BASELINE = STATE / "baseline.json"
LIMIT = 256 << 20  # larger files are recorded by metadata only


class Refused(RuntimeError):
    pass


def describe(path: Path) -> dict:
    info = path.lstat()
    entry = {"uid": info.st_uid, "gid": info.st_gid, "mode": oct(stat.S_IMODE(info.st_mode))}
    if stat.S_ISLNK(info.st_mode):
        entry["type"] = "link"
        entry["target"] = os.readlink(path)
    elif stat.S_ISREG(info.st_mode):
        entry["type"] = "file"
        if info.st_size <= LIMIT:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            entry["sha256"] = digest.hexdigest()
        else:
            entry["size"] = info.st_size
    elif stat.S_ISDIR(info.st_mode):
        entry["type"] = "dir"
    else:
        entry["type"] = "other"
    return entry


def snapshot(paths: list[str]) -> dict[str, dict]:
    state: dict[str, dict] = {}
    for root in paths:
        base = Path(root)
        if not base.is_absolute():
            raise Refused(f"{root} is not an absolute path")
        if not os.path.lexists(base):
            state[str(base)] = {"type": "missing"}
            continue
        if base.is_dir() and not base.is_symlink():
            for directory, dirs, files in os.walk(base, followlinks=False):
                dirs.sort()
                state[directory] = describe(Path(directory))
                for name in sorted(files):
                    path = Path(directory) / name
                    state[str(path)] = describe(path)
                for name in dirs:
                    path = Path(directory) / name
                    if path.is_symlink():
                        state[str(path)] = describe(path)
        else:
            state[str(base)] = describe(base)
    return state


def differences(before: dict[str, dict], after: dict[str, dict]) -> list[str]:
    report = []
    for path in sorted(set(before) | set(after)):
        if path not in after:
            report.append(f"removed  {path}")
        elif path not in before:
            report.append(f"added    {path}")
        elif before[path] != after[path]:
            changed = sorted(key for key in set(before[path]) | set(after[path])
                             if before[path].get(key) != after[path].get(key))
            report.append(f"changed  {path} ({', '.join(changed)})")
    return report


def config_paths() -> list[str]:
    data = json.loads(CONFIG.read_text())
    paths = data.get("paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise Refused(f"{CONFIG} names no paths")
    return paths


def write_baseline(state: dict) -> None:
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE, 0o700)
    temporary = BASELINE.with_suffix(".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(state, handle, sort_keys=True)
    os.replace(temporary, BASELINE)


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) == 2 else ""
    try:
        if command in ("baseline", "accept"):
            state = snapshot(config_paths())
            write_baseline(state)
            print(f"hyperlab-integrity: {command}: {len(state)} entries recorded")
            return 0
        if command == "check":
            if not BASELINE.is_file() or BASELINE.is_symlink():
                raise Refused("no baseline; run hyperlab-integrity baseline")
            before = json.loads(BASELINE.read_text())
            report = differences(before, snapshot(config_paths()))
            for line in report:
                print(f"hyperlab-integrity: {line}")
            if report:
                print(f"hyperlab-integrity: {len(report)} differences from the baseline")
                return 1
            print("hyperlab-integrity: no difference from the baseline")
            return 0
    except (Refused, OSError, ValueError) as exc:
        print(f"hyperlab-integrity: {exc}", file=sys.stderr)
        return 2
    print("usage: hyperlab-integrity baseline|check|accept", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
