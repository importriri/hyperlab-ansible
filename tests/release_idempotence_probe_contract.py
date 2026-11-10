#!/usr/bin/env python3
"""Host-independent contracts for Ansible recap evidence."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from release_acceptance import AcceptanceError  # noqa: E402
from release_probe import idempotence_payload, parse_ansible_recap  # noqa: E402


def recap(
    changed: int = 0,
    unreachable: int = 0,
    failed: int = 0,
    *,
    ansi: bool = False,
) -> str:
    line = (
        "localhost : ok=10 changed="
        f"{changed} unreachable={unreachable} failed={failed} "
        "skipped=1 rescued=0 ignored=0"
    )
    if ansi:
        line = f"\x1b[0;32m{line}\x1b[0m"
    return f"PLAY [fixture]\n\nPLAY RECAP\n{line}\n"


def test_three_successful_recaps_produce_the_host_idempotence_payload() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        check = root / "check.log"
        first = root / "first.log"
        second = root / "second.log"
        check.write_text(recap(changed=4), encoding="utf-8")
        first.write_text(recap(changed=9), encoding="utf-8")
        second.write_text(recap(changed=0, ansi=True), encoding="utf-8")

        assert parse_ansible_recap(second) == [
            {
                "host": "localhost",
                "ok": 10,
                "changed": 0,
                "unreachable": 0,
                "failed": 0,
            }
        ]
        payload = idempotence_payload(check, first, second)
        assert payload["second_apply_changed_zero"] is True
        for field in (
            "check_mode_sha256",
            "first_apply_sha256",
            "second_apply_sha256",
        ):
            assert len(payload[field]) == 64


def test_changed_failed_unreachable_and_missing_recaps_are_refused() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        check = root / "check.log"
        first = root / "first.log"
        second = root / "second.log"
        check.write_text(recap(), encoding="utf-8")
        first.write_text(recap(), encoding="utf-8")
        cases = [
            (recap(changed=1), "not idempotent"),
            (recap(failed=1), "not successful"),
            (recap(unreachable=1), "not successful"),
            ("log without a recap\n", "no PLAY RECAP"),
        ]
        for content, message in cases:
            second.write_text(content, encoding="utf-8")
            try:
                idempotence_payload(check, first, second)
            except AcceptanceError as exc:
                assert message in str(exc)
            else:
                raise AssertionError(f"invalid recap accepted: {message}")


def test_real_idempotence_cli_supports_both_campaign_versions() -> None:
    import json
    import subprocess
    from release_acceptance import load_yaml, validate_gate_payload
    from release_probe import gate_contract
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        logs = [root / name for name in ("check.log", "first.log", "second.log")]
        for path, changed in zip(logs, (4, 9, 0), strict=True):
            path.write_text(recap(changed=changed))
        for version in (2, 3):
            manifest = ROOT / f"release/acceptance.v{version}.yml"
            argv = [sys.executable, str(ROOT / "tools/release_probe.py"), "--manifest", str(manifest),
                    "idempotence", "--check-log", str(logs[0]), "--first-apply-log", str(logs[1]),
                    "--second-apply-log", str(logs[2])]
            result = subprocess.run(argv, text=True, capture_output=True, check=False)
            assert result.returncode == 0, result.stderr
            payload = json.loads(result.stdout)
            validate_gate_payload(gate_contract(load_yaml(manifest), "host-idempotence"), payload, complete=True)
            assert payload["second_apply_changed_zero"] is True
            logs[2].write_text(recap(changed=1))
            refused = subprocess.run(argv, text=True, capture_output=True, check=False)
            assert refused.returncode == 2 and "not idempotent" in refused.stderr
            logs[2].write_text(recap())


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"release idempotence probe contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
