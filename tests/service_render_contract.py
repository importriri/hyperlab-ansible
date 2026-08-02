#!/usr/bin/env python3
"""Render the M7 services network and prove DHCP host drift is detected."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "roles/network_domains/templates"
COMPARATOR = ROOT / "roles/network_domains/files/network_xml_equivalent.py"


def regex_replace(value: object, pattern: str, replacement: str) -> str:
    """Mirror the Ansible filter used by the production network template."""
    return re.sub(pattern, replacement, str(value))


def main() -> int:
    networks = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())
    services_contract = yaml.safe_load((ROOT / "group_vars/all/services.yml").read_text())
    service_domain = next(item for item in networks["network_domains"] if item["name"] == "services")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_ROOT)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    env.filters["regex_replace"] = regex_replace
    rendered = env.get_template("net.xml.j2").render(
        item=service_domain,
        service_dhcp_leases=services_contract["service_dhcp_leases"],
    )
    root = ET.fromstring(rendered)
    hosts = [node.attrib for node in root.findall("./ip/dhcp/host")]
    assert hosts == [{
        "mac": "52:54:00:66:29:6e",
        "name": "svc-jellyfin",
        "ip": "10.10.5.10",
    }]

    with tempfile.TemporaryDirectory() as td:
        desired = Path(td) / "desired.xml"
        drifted = Path(td) / "drifted.xml"
        desired.write_text(rendered, encoding="utf-8")
        drifted.write_text(rendered.replace("10.10.5.10", "10.10.5.11"), encoding="utf-8")
        equal = subprocess.run(
            [sys.executable, str(COMPARATOR), str(desired), str(desired)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert equal.returncode == 0, equal.stderr
        drift = subprocess.run(
            [sys.executable, str(COMPARATOR), str(desired), str(drifted)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert drift.returncode == 1 and "dhcp_hosts" in drift.stdout
    print("service render contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
