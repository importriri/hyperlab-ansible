#!/usr/bin/env python3
"""Structural contract for performance tuning and Secure Boot acceptance."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

README = (ROOT / "README.md").read_text(encoding="utf-8")
PROBLEM_INDEX = (ROOT / "problems/README.md").read_text(encoding="utf-8")
HISTORICAL = (ROOT / "docs/historical-audit-m0.md").read_text(encoding="utf-8")
VFIO = (ROOT / "roles/vfio_boot/defaults/main.yml").read_text(encoding="utf-8")

for doc in (
    "docs/performance-security-contract.md",
    "docs/nitro-secure-boot-acceptance.md",
):
    assert f"({doc})" in README, f"{doc} must stay reachable from README.md"

for problem in (
    "sbctl-export-enrolled-keys-landlock.md",
    "operator-shell-strict-mode-leak.md",
    "secure-boot-enrollment-handoff.md",
    "dkms-module-signing-trust.md",
):
    assert f"({problem})" in PROBLEM_INDEX, f"{problem} must stay in the problem index"

assert "produces an encrypted, Secure Boot host and stops" not in HISTORICAL
assert "firmware enrollment" in HISTORICAL
assert "hardware acceptance gate" in HISTORICAL

vfio_profile, remainder = VFIO.split("  - file: Arch-Linux-Hardened.conf", 1)
assert "intel_iommu=on iommu=pt" in vfio_profile
assert "lockdown=" not in vfio_profile, (
    "Secure Boot and lockdown are separate Nitro acceptance gates; do not "
    "silently add lockdown to the VFIO default"
)
assert "lockdown=confidentiality" in remainder

forbidden = (
    "mitigations=off",
    "spectre_v2=off",
    "mds=off",
    "l1tf=off",
    "tsx_async_abort=off",
    "split_lock_detect=off",
    "disable_splitlock=1",
)

runtime_roots = (
    ROOT / "roles",
    ROOT / "group_vars",
    ROOT / "playbooks",
    ROOT / "tools",
)

for base in runtime_roots:
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".webp", ".zip"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in forbidden:
            assert token not in text, (
                f"{path.relative_to(ROOT)} contains forbidden performance "
                f"weakening {token!r}"
            )

print("performance/security contract: OK")
