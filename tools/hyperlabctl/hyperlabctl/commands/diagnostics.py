"""Collect one Machine's host and guest logs into one archive, redacted.

`hyperlabctl diagnostics collect NAME` gathers what an operator needs to
describe a problem with one Machine: from the host, its inactive domain
XML, state, inventory row and operation records, and the system journal
lines that name it; from the guest, over the pinned SSH channel and read
only, its journals, the Looking Glass sender's logs, failed units, disk and
memory. Every text passes the redactor before it is written: private keys,
password and token assignments, password hashes, known token formats and
email addresses are replaced. Nothing is read from seeds, runtime access
files or SSH keys. The archive is private (0600) and its manifest lists
what was collected, what could not be, and how much was redacted in each
file.
"""

import io
import json
import os
import re
import subprocess
import tarfile
import time
from pathlib import Path

from ..errors import ContractError, Unavailable
from .base import Command
from .open import _ssh_argv, _wait_for_ssh_ready

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
OUTPUT = Path.home() / "hyperlab-evidence" / "diagnostics"
LIMIT = 4 << 20  # bytes kept from one source

REDACTIONS = (
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
     "[private key redacted]"),
    (re.compile(r"(?i)\b(authorization:\s*(?:bearer|basic)\s+)\S+"), r"\1[redacted]"),
    (re.compile(r"(?i)\b(password|passwd|passphrase|secret|token|api[_-]?key|access[_-]?key)"
                r"(\"?\s*[:=]\s*\"?)[^\s\"',;]+"), r"\1\2[redacted]"),
    (re.compile(r"\$(?:1|2[abxy]|5|6|7|y|gy)\$[^\s:'\"]+"), "[password hash redacted]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "[token redacted]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[token redacted]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), "[token redacted]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[token redacted]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "[token redacted]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[email redacted]"),
)

GUEST_SOURCES = {
    "guest/journal-user.txt": "journalctl --user -b --no-pager -o short-iso -n 3000",
    "guest/journal-system-warnings.txt": "journalctl -b --no-pager -o short-iso -p warning -n 1000",
    "guest/failed-units.txt": "systemctl --failed --no-pager; systemctl --user --failed --no-pager",
    "guest/looking-glass-host.log": "tail -n 2000 ~/.local/state/hyperlab/looking-glass-host.log",
    "guest/looking-glass-host.log.1": "tail -n 2000 ~/.local/state/hyperlab/looking-glass-host.log.1",
    "guest/resources.txt": "uptime; free -m; df -h -x tmpfs -x devtmpfs",
}


def redact(text):
    """The text with secrets replaced, and how many replacements were made."""
    count = 0
    for pattern, replacement in REDACTIONS:
        text, made = pattern.subn(replacement, text)
        count += made
    return text, count


def _run(argv, run, timeout=30, stdin=None):
    try:
        result = run(argv, capture_output=True, text=True, timeout=timeout, check=False, input=stdin)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or "exit %d" % result.returncode).strip()[-300:]
    return result.stdout, ""


def host_sources(name, run):
    sources = {
        "host/domain.xml": ["virsh", "--connect", "qemu:///system", "-r", "dumpxml", "--inactive", name],
        "host/domain-state.txt": ["virsh", "--connect", "qemu:///system", "-r", "domstate", "--reason", name],
        "host/domain-info.txt": ["virsh", "--connect", "qemu:///system", "-r", "dominfo", name],
        "host/machine-inventory.json": ["hyperlabctl", "--json", "machine", "inventory"],
        "host/journal-system.txt": ["journalctl", "-b", "--no-pager", "-o", "short-iso", "-n", "20000",
                                    "--grep", re.escape(name)],
    }
    collected = {}
    for path, argv in sources.items():
        collected[path] = _run(argv, run)
    inventory, error = collected["host/machine-inventory.json"]
    if inventory is not None:
        try:
            rows = json.loads(inventory).get("machines", [])
            row = [r for r in rows if isinstance(r, dict) and r.get("name") == name]
            collected["host/machine-inventory.json"] = (json.dumps(row, indent=2) + "\n", "")
        except (ValueError, AttributeError):
            collected["host/machine-inventory.json"] = (None, "the inventory was not JSON")
    return collected


def operation_records(name):
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())) / "hyperlab" / "operations"
    records = []
    for path in sorted(runtime.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get("machine") == name:
            records.append(record)
    return json.dumps(records, indent=2) + "\n", ""


def guest_sources(ctx, name, run):
    try:
        ssh_argv = _ssh_argv(ctx, name)
        _wait_for_ssh_ready(ssh_argv, name)
    except (Unavailable, ContractError, OSError) as exc:
        return dict.fromkeys(GUEST_SOURCES, (None, "no SSH to the guest: %s" % exc))
    return {path: _run([*ssh_argv, command], run, timeout=60) for path, command in GUEST_SOURCES.items()}


def collect(ctx, name, run=subprocess.run, output=OUTPUT, now=None, with_guest=True):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ContractError("invalid Machine name")
    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime(now if now is not None else time.time()))
    sources = host_sources(name, run)
    sources["host/operations.json"] = operation_records(name)
    if with_guest:
        sources.update(guest_sources(ctx, name, run))
    manifest = {"machine": name, "collected_at": stamp, "files": {}, "missing": {}}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, (text, error) in sorted(sources.items()):
            if text is None:
                manifest["missing"][path] = redact(error)[0]
                continue
            clean, count = redact(text[-LIMIT:])
            data = clean.encode()
            info = tarfile.TarInfo("%s-%s/%s" % (name, stamp, path))
            info.size, info.mode, info.mtime = len(data), 0o600, int(time.time())
            archive.addfile(info, io.BytesIO(data))
            manifest["files"][path] = {"bytes": len(data), "redactions": count,
                                       "truncated": len(text) > LIMIT}
        data = (json.dumps(manifest, indent=2) + "\n").encode()
        info = tarfile.TarInfo("%s-%s/manifest.json" % (name, stamp))
        info.size, info.mode, info.mtime = len(data), 0o600, int(time.time())
        archive.addfile(info, io.BytesIO(data))
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    target = output / ("%s-%s.tar.gz" % (name, stamp))
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(buffer.getvalue())
    return target, manifest


class DiagnosticsCommand(Command):
    name = "diagnostics"
    help = "collect one Machine's host and guest logs into a redacted archive"
    order = 41

    def configure(self, parser):
        sub = parser.add_subparsers(dest="diagnostics_action", required=True)
        target = sub.add_parser("collect", help="one private, redacted archive for one Machine")
        target.add_argument("machine")
        target.add_argument("--host-only", action="store_true", help="do not reach into the guest")

    def run(self, args, ctx):
        path, manifest = collect(ctx, args.machine, with_guest=not args.host_only)
        if args.json:
            print(json.dumps({"archive": str(path), **manifest}))
        else:
            redactions = sum(entry["redactions"] for entry in manifest["files"].values())
            print("%s: %d files, %d redactions, %d not collected" % (
                path, len(manifest["files"]), redactions, len(manifest["missing"])))
        return 0
