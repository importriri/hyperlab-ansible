"""Reading the journal, because the per-domain qemu logs are not ours to read.

/var/log/libvirt/qemu/<domain>.log is root:root 0600. The panel runs in the
session, so it reads the journal instead: systemd grants the wheel and adm
groups an ACL on /var/log/journal, and the base role already puts the admin
user in wheel.
"""

import json

from .errors import Unavailable

UNITS = ("virtqemud", "libvirtd", "virtnetworkd")

PRIORITY = {"0": "error", "1": "error", "2": "error", "3": "error",
            "4": "warn", "5": "info", "6": "info", "7": "debug"}


def read(ctx, lines=40, units=None):
    units = units or getattr(ctx.config, "journal_units", UNITS)
    argv = [ctx.config.journalctl_bin, "--no-pager", "-o", "json", "-n", str(lines)]
    for unit in units:
        argv += ["-u", unit]
    result = ctx.runner.run(argv)
    if result.rc == 127:
        raise Unavailable("journalctl is not installed")
    if not result.ok:
        raise Unavailable("journal is unreadable: %s"
                          % (result.stderr.strip() or "permission denied"))
    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        stamp = record.get("__REALTIME_TIMESTAMP")
        when = ""
        if stamp:
            try:
                import datetime
                when = datetime.datetime.fromtimestamp(
                    int(stamp) / 1_000_000).strftime("%H:%M:%S")
            except (ValueError, OSError):
                when = ""
        message = record.get("MESSAGE")
        if isinstance(message, list):
            message = "".join(chr(byte) for byte in message)
        entries.append({
            "time": when,
            "level": PRIORITY.get(str(record.get("PRIORITY", "6")), "info"),
            "unit": record.get("_SYSTEMD_UNIT", "") or record.get("SYSLOG_IDENTIFIER", ""),
            "message": (message or "").strip(),
        })
    return entries
