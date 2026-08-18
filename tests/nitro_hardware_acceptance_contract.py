#!/usr/bin/env python3
"""Keep the accepted AN515-55 lifecycle evidence and its limits visible."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = (ROOT / "docs/nitro-an515-55-hardware.md").read_text(
    encoding="utf-8"
)
PROCEDURE = (ROOT / "docs/nitro-sense-procedure.md").read_text(
    encoding="utf-8"
)
PROCEDURE_FLAT = " ".join(PROCEDURE.split())
PROBLEM_INDEX = (ROOT / "problems/README.md").read_text(encoding="utf-8")

INCIDENTS = (
    "ansible-become-password-handoff.md",
    "nitro-suspend-resume-evidence-race.md",
    "nitro-wmi-unknown-function-four.md",
)


def main() -> int:
    for incident in INCIDENTS:
        assert (ROOT / "problems" / incident).is_file(), (
            f"Nitro acceptance incident is missing: {incident}"
        )
        assert incident in PROBLEM_INDEX, (
            f"Nitro acceptance incident is not indexed: {incident}"
        )

    for fragment in (
        "`PM: suspend exit`",
        "`wlan0` was `UP,LOWER_UP`",
        "rollback: `ok=46`, `changed=10`, `failed=0`",
        "reinstall: `ok=113`, `changed=32`, `failed=0`",
        "second run: `ok=91`, `changed=0`, `failed=0`",
        "Unknown function number - 4 - 0",
    ):
        assert fragment in HARDWARE, (
            f"Nitro hardware evidence omits: {fragment}"
        )

    for fragment in (
        "kernel `PM: suspend exit`",
        "Service state is not a substitute for value readback.",
        "Reinstall only after rollback and platform-function recovery are proved.",
    ):
        assert fragment in PROCEDURE_FLAT, (
            f"Nitro procedure omits lifecycle rule: {fragment}"
        )

    print("Nitro hardware acceptance contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
