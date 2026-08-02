"""Every problem a provider can raise must carry a remedy.

Scanned from the provider sources rather than typed here: a new problem id
arrives with its own test, and forgetting the remedy is what turns this red.
"""

import re
from pathlib import Path

from harness import check, equals
from hyperlabctl import providers
from hyperlabctl.remedies import REMEDIES

SOURCE = Path(providers.__file__).parent


def declared_ids():
    found = set()
    for module in sorted(SOURCE.glob("*.py")):
        found |= set(re.findall(r'"id":\s*"([a-z_]+\.[a-z_]+)"', module.read_text()))
    return found


def test_the_scan_actually_finds_problem_ids():
    check("scan_not_empty", len(declared_ids()) >= 6)


def test_every_declared_problem_id_has_a_remedy():
    missing = sorted(declared_ids() - set(REMEDIES))
    equals("no_problem_without_a_remedy", missing, [])


def test_the_generic_failure_ids_are_covered_too():
    for generic in ("hyperlab.unavailable", "hyperlab.contract", "provider.crashed"):
        check("generic_%s_covered" % generic, generic in REMEDIES)
