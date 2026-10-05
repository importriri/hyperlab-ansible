#!/usr/bin/env python3
"""No Machine gets the host's microphone, camera or USB devices by default.

Roadmap milestone 6 keeps them off until a host action turns one on for one
Machine (ADR 0034, ADR 0035, both proposed). This contract holds the default:

  1. the Looking Glass client denies the microphone, with no prompt, and no
     guest gets a capture device: the sound card is playback only, and a
     domain defined before that is recognised as legacy and reconciled;
  2. the domain template passes no USB device, redirects no USB over SPICE,
     shares no folder and allows no SPICE file transfer;
  3. every checked-in VM spec keeps its USB allowlist empty and shares no
     folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    opener = (ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py").read_text()
    require('"audio:micDefault=deny",' in opener, "Looking Glass does not deny the microphone")
    for permissive in ("micDefault=allow", "micDefault=prompt"):
        require(permissive not in opener, f"Looking Glass may offer the microphone ({permissive})")

    template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text()
    require('<codec type="output"/>' in template, "the guest sound card is not playback only")
    for codec in ("duplex", "micro"):
        require(f'<codec type="{codec}"/>' not in template, f"a guest gets a {codec} capture device")
    validate = (ROOT / "roles/guest/tasks/validate.yml").read_text()
    require("--allow-legacy-duplex-codec" in validate
            and "guest_has_legacy_duplex_codec and\n              guest_operation == 'create' and\n              guest_domain_state == 'shut off'" in validate,
            "a legacy duplex domain is neither recognised nor reconciled when shut off")
    for needle, why in (
        ('type="usb"', "a USB device is passed to every guest"),
        ("<redirdev", "USB is redirected over SPICE"),
        ("<filesystem", "a host folder is shared with every guest"),
    ):
        require(needle not in template.replace('<input type="tablet" bus="usb"/>', ""), why)
    require('<filetransfer enable="no"/>' in template, "SPICE file transfer is not off")

    for path in sorted((ROOT / "vm-specs").glob("*.yml")):
        spec = yaml.safe_load(path.read_text())
        require(spec.get("usb_allowlist") == [], f"{path.name} passes a USB device")
        require(spec.get("shared_folders") is False, f"{path.name} shares a folder")
    print("Media input contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
