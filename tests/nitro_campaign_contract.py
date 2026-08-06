#!/usr/bin/env python3
"""The Nitro VFIO campaign must preserve recovery and phased guest boot."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs/nitro-arch-dev-vfio-campaign.md"
ACCELERATION = ROOT / "docs/arch-dev-acceleration.md"


def main() -> int:
    text = RUNBOOK.read_text(encoding="utf-8")
    acceleration = ACCELERATION.read_text(encoding="utf-8")
    acceleration_flat = " ".join(acceleration.split())

    for fragment in (
        "`qemu:///system`",
        "`arch-dev-vfio`",
        "`arch-dev` remains",
        "`balanced` (8 GiB)",
        "`heavy`\n  (16 GiB)",
        "guest `2,6,3,7`",
        "emulator `0,4`",
        "disk I/O `1,5`",
        "loopback SPICE",
        "workstation_kernel_remove_fallback=false",
        "playbooks/guest-arch-dev-vfio.yml",
        "ARCH_DEV_VFIO_HOST_GATE_OK",
        "ARCH_DEV_VFIO_GUEST_GATE_OK",
        "playbooks/guest-visual-assets.yml",
        "Do not create a systemd sender unit",
    ):
        assert fragment in text, f"Nitro campaign omits: {fragment}"

    for path in (
        "vm-specs/arch-dev-vfio.yml",
        "playbooks/guest-arch-dev-vfio.yml",
        "playbooks/guest-visual-assets.yml",
        "tools/nitro/arch_dev_vfio_host_gate.py",
        "tools/nitro/arch_dev_vfio_guest_gate.py",
    ):
        assert (ROOT / path).is_file(), f"Nitro campaign target is missing: {path}"

    assert "playbooks/vm-destroy.yml" not in text
    assert "systemctl enable looking-glass-host" not in text

    for fragment in (
        "share one IOMMU group",
        "viable VFIO group",
        "class `0604`",
        "`pcieport`",
        "any other peer using a host driver",
    ):
        assert fragment in acceleration_flat, (
            f"Acceleration document omits VFIO policy: {fragment}"
        )

    assert "no peer in either" not in acceleration_flat
    assert (
        "IOMMU group remains attached to a host driver"
        not in acceleration_flat
    )

    print("Nitro acceleration campaign contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
