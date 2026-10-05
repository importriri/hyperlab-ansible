#!/usr/bin/env python3
"""The threat model lists every open problem and claims no Qubes OS properties.

docs/threat-model.md is the page a reviewer reads first. It must say that
HyperLab does not provide Qubes OS security properties and never claim the
opposite; it must link every note in problems/ whose status is open; every
test it names as evidence must exist; and SECURITY.md must route reports
privately and point at it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs/threat-model.md"
OVERCLAIMS = (
    r"as secure as qubes", r"qubes[- ]level", r"equivalent to qubes", r"qubes[- ]grade",
    r"(?<!not )(?<!never )provides? (the )?(same )?qubes", r"like qubes os,? hyperlab (isolates|guarantees)",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    text = PAGE.read_text()
    lower = text.lower()
    require("does not provide qubes os security properties" in lower,
            "the threat model does not say it lacks Qubes OS security properties")
    for pattern in OVERCLAIMS:
        require(re.search(pattern, lower) is None, f"the threat model overclaims: {pattern}")
    for note in sorted((ROOT / "problems").glob("*.md")):
        status = next((line for line in note.read_text().splitlines() if line.startswith("Status:")), "")
        if re.match(r"Status: open\b", status, re.I):
            require(f"problems/{note.name}" in text, f"open problem {note.name} is missing from the threat model")
    for test in sorted(set(re.findall(r"`(tests/[a-z0-9_.]+)`", text))):
        require((ROOT / test).is_file(), f"the threat model cites {test}, which does not exist")
    policy = (ROOT / "SECURITY.md").read_text()
    require("/security/advisories/new" in policy and "docs/threat-model.md" in policy,
            "SECURITY.md does not route reports privately or point at the threat model")
    require("does not provide qubes os security properties" in policy.lower(),
            "SECURITY.md does not state the Qubes OS boundary")
    print("Threat model contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
