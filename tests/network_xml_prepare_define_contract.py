#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "roles/network_domains/files/network_xml_prepare_define.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("network_xml_prepare_define", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    tool = load_tool()
    current = """<network>
  <name>services</name>
  <uuid>1f077ea4-e7e9-4e0a-b181-649810c86cd3</uuid>
  <forward mode='nat'/>
  <bridge name='virbr-services' stp='on' delay='0'/>
  <mac address='52:54:00:8f:57:5f'/>
  <ip address='10.10.5.1' netmask='255.255.255.0'>
    <dhcp><range start='10.10.5.100' end='10.10.5.199'/></dhcp>
  </ip>
</network>"""
    desired = """<network>
  <name>services</name>
  <bridge name='virbr-services' stp='on' delay='0'/>
  <forward mode='nat'/>
  <ip address='10.10.5.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='10.10.5.100' end='10.10.5.199'/>
      <host mac='52:54:00:66:29:6e' name='svc-jellyfin' ip='10.10.5.10'/>
    </dhcp>
  </ip>
</network>"""

    prepared = tool.preserve_identity(desired, current)
    root = ET.fromstring(prepared)
    assert root.findtext("uuid") == "1f077ea4-e7e9-4e0a-b181-649810c86cd3"
    assert root.find("mac").get("address") == "52:54:00:8f:57:5f"
    host = root.find("./ip/dhcp/host")
    assert host is not None
    assert host.attrib == {
        "mac": "52:54:00:66:29:6e",
        "name": "svc-jellyfin",
        "ip": "10.10.5.10",
    }

    fresh = ET.fromstring(tool.preserve_identity(desired, ""))
    assert fresh.find("uuid") is None
    assert fresh.find("mac") is None

    try:
        tool.preserve_identity(desired.replace("services", "other", 1), current)
    except ValueError as exc:
        assert "name mismatch" in str(exc)
    else:
        raise AssertionError("name mismatch was accepted")

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "network.xml"
        tool.atomic_write(output, prepared)
        assert output.stat().st_mode & 0o777 == 0o600
        assert output.read_text() == prepared

    print("network XML prepare-define contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
