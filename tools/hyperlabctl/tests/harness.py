"""Counters and assertions. No pytest: the suite runs anywhere python does."""

import sys
import traceback

PASSED = 0
FAILED = 0
FAILURES = []


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
    else:
        FAILED += 1
        FAILURES.append("%s%s" % (name, " -- %s" % detail if detail else ""))


def equals(name, actual, expected):
    check(name, actual == expected, "expected %r, got %r" % (expected, actual))


def run_module(module):
    for attribute in sorted(dir(module)):
        if not attribute.startswith("test_"):
            continue
        function = getattr(module, attribute)
        try:
            function()
        except Exception:  # noqa: BLE001 - one failing test must not end the run
            check(attribute, False, "raised:\n%s" % traceback.format_exc())


def report():
    print("passed %d, failed %d" % (PASSED, FAILED))
    for failure in FAILURES:
        print("  FAIL %s" % failure)
    return 1 if FAILED else 0


def main(modules):
    for module in modules:
        run_module(module)
    sys.exit(report())
