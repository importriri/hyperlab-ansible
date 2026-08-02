#!/usr/bin/env python3
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "roles/network_domains/tasks/main.yml"
DEFAULTS = ROOT / "roles/network_domains/defaults/main.yml"
PREPARER = ROOT / "roles/network_domains/files/network_xml_prepare_define.py"


def main() -> int:
    data = yaml.safe_load(TASKS.read_text())
    names = [task.get("name") for task in data]
    prepare_i = names.index("Prepare definitions with the existing libvirt identity")
    stop_i = names.index("Stop changed active networks for immediate reconciliation")
    define_i = names.index("Define missing or changed persistent networks")
    active_i = names.index("Activate every network domain")
    assert prepare_i < stop_i < define_i < active_i

    prepare = data[prepare_i]
    prepare_cmd = prepare["ansible.builtin.command"]
    assert prepare_cmd["argv"] == [
        "{{ network_domains_prepare_tool }}",
        "{{ network_domains_config_dir }}/{{ item.item.name }}.xml",
        "-",
        "{{ network_domains_runtime_dir }}/{{ item.item.name }}.xml",
    ]
    assert prepare_cmd["stdin"] == "{{ item.stdout if item.rc == 0 else '' }}"
    assert prepare["loop"] == "{{ network_domains_current_xml.results }}"
    assert prepare["changed_when"] is False
    assert prepare["check_mode"] is False

    define = data[define_i]
    define_cmd = define["ansible.builtin.command"]
    assert define_cmd["argv"] == [
        "virsh",
        "net-define",
        "{{ network_domains_runtime_dir }}/{{ item }}.xml",
    ]
    assert define["loop"] == "{{ network_domains_reconcile }}"
    assert define["changed_when"] is True
    assert "community.libvirt.virt_net" not in define

    defaults = yaml.safe_load(DEFAULTS.read_text())
    assert defaults["network_domains_prepare_tool"].endswith(
        "privatestack-network-xml-prepare-define"
    )
    assert defaults["network_domains_runtime_dir"].startswith("/run/")
    assert PREPARER.is_file()

    text = TASKS.read_text()
    assert "command: define" not in text
    assert "{{ network_domains_config_dir }}/{{ item }}.xml" not in text.split(
        "- name: Define missing or changed persistent networks", 1
    )[1]
    print("network domains contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
