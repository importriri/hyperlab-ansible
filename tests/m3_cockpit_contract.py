#!/usr/bin/env python3
"""Pin the contract between M3's managed XML and the cockpit surfaces."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/hyperlabctl"
sys.path.insert(0, str(TOOL))


def main() -> int:
    from hyperlabctl.domainxml import HL, HL_LEGACY, parse_domain
    from hyperlabctl.errors import Unavailable
    from hyperlabctl.registry import by_id

    domain_template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text(encoding="utf-8")
    operations = (TOOL / "hyperlabctl/operations.py").read_text(encoding="utf-8")

    assert 'xmlns:hyperlab="%s"' % HL in domain_template
    assert "M3 lifecycle playbook" in operations

    metadata_attributes = (
        "schema='1' lifecycle='permanent' device-profile='vfio' network-profile='dev'"
    )
    legacy = parse_domain(
        "<domain><name>legacy</name><metadata>"
        "<hyperlab:instance xmlns:hyperlab='%s' %s/>"
        "</metadata><devices/></domain>" % (HL_LEGACY, metadata_attributes)
    )
    assert legacy["managed"] is True
    assert legacy["device_profile"] == "vfio"
    assert legacy["lifecycle"] == "permanent"

    foreign = parse_domain(
        "<domain><metadata><foreign:instance xmlns:foreign='urn:foreign' %s/>"
        "</metadata><devices/></domain>" % metadata_attributes
    )
    assert foreign["managed"] is False

    try:
        parse_domain(
            "<domain><metadata>"
            "<current:instance xmlns:current='%s' %s/>"
            "<legacy:instance xmlns:legacy='%s' %s/>"
            "</metadata><devices/></domain>"
            % (HL, metadata_attributes, HL_LEGACY, metadata_attributes)
        )
    except Unavailable as exc:
        assert "multiple supported HyperLab metadata instances" in str(exc)
    else:
        raise AssertionError("duplicate managed metadata was accepted")

    expected = {
        "vm.create": "playbooks/vm-create.yml",
        "vm.destroy": "playbooks/vm-destroy.yml",
        "vm.validate": "playbooks/vm-validate.yml",
        "vm.managed-start": "playbooks/vm-start.yml",
        "vm.managed-shutdown": "playbooks/vm-shutdown.yml",
        "vm.managed-reboot": "playbooks/vm-reboot.yml",
        "vm.resize": "playbooks/vm-resize-disk.yml",
        "vm.reconfigure": "playbooks/vm-reconfigure.yml",
        "vm.force-stop": "playbooks/vm-stop.yml",
        "vm.power-cycle": "playbooks/vm-power-cycle.yml",
        "vm.reset": "playbooks/vm-reset.yml",
    }
    for action_id, playbook in expected.items():
        action = by_id(action_id)
        assert action is not None
        assert action["privileged"] is True
        assert action["requires"] == playbook
        assert playbook in action["command"]
        assert (ROOT / playbook).is_file()

    assert by_id("vm.destroy")["destructive"] is True
    assert by_id("vm.force-stop")["destructive"] is True
    assert by_id("vm.reset")["destructive"] is True
    assert by_id("vm.resize")["destructive"] is True
    assert by_id("vm.reconfigure")["destructive"] is False

    print("M3 cockpit contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
