#!/usr/bin/env python3
"""Pin the contract between M3's managed XML and the cockpit surfaces."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/hyperlabctl"
sys.path.insert(0, str(TOOL))


def main() -> int:
    from hyperlabctl.domainxml import HL
    from hyperlabctl.registry import by_id

    domain_template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text(encoding="utf-8")
    operations = (TOOL / "hyperlabctl/operations.py").read_text(encoding="utf-8")

    assert 'xmlns:hyperlab="%s"' % HL in domain_template
    assert "M3 lifecycle playbook" in operations

    expected = {
        "vm.create": "playbooks/vm-create.yml",
        "vm.destroy": "playbooks/vm-destroy.yml",
        "vm.validate": "playbooks/vm-validate.yml",
        "vm.managed-start": "playbooks/vm-start.yml",
        "vm.managed-shutdown": "playbooks/vm-shutdown.yml",
        "vm.force-stop": "playbooks/vm-stop.yml",
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

    print("M3 cockpit contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
