"""The journal is the only log source the session can read."""

import world
from harness import check, equals
from hyperlabctl import journal
from hyperlabctl.errors import Unavailable

ENTRY = ('{"__REALTIME_TIMESTAMP":"1753731842000000","PRIORITY":"4",'
         '"_SYSTEMD_UNIT":"virtqemud.service","MESSAGE":"domain started"}')
DEBUG = ('{"__REALTIME_TIMESTAMP":"1753731843000000","PRIORITY":"7",'
         '"_SYSTEMD_UNIT":"virtqemud.service","MESSAGE":"noise"}')


def _ctx(payload, rc=0):
    ctx = world.build(trust=None)
    argv = ["/usr/bin/journalctl", "--no-pager", "-o", "json", "-n", "40"]
    for unit in journal.UNITS:
        argv += ["-u", unit]
    ctx.runner.register(argv, (rc, payload) if rc else payload)
    return ctx


def test_journal_maps_priority_to_a_level():
    entries = journal.read(_ctx(ENTRY + "\n" + DEBUG))
    equals("warn_level", entries[0]["level"], "warn")
    equals("debug_level", entries[1]["level"], "debug")


def test_journal_keeps_the_message_and_the_time():
    entries = journal.read(_ctx(ENTRY))
    equals("message", entries[0]["message"], "domain started")
    check("time_is_hhmmss", len(entries[0]["time"]) == 8)


def test_journal_skips_lines_that_are_not_json():
    entries = journal.read(_ctx("not json\n" + ENTRY))
    equals("only_the_valid_line", len(entries), 1)


def test_journal_missing_binary_degrades_rather_than_crashing():
    ctx = world.build(trust=None)
    try:
        journal.read(ctx)
        check("missing_journalctl_raises_unavailable", False, "no exception")
    except Unavailable as exc:
        check("missing_journalctl_message", "journalctl" in str(exc))


def test_journal_permission_failure_says_so():
    try:
        journal.read(_ctx("", rc=1))
        check("denied_raises", False, "no exception")
    except Unavailable as exc:
        check("denied_message", "unreadable" in str(exc))
