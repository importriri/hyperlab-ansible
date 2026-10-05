#!/usr/bin/env python3
"""No display server listens beyond loopback, and no Template turns on the
SPICE clipboard.

  1. The domain template, rendered for a standard and a VFIO Machine, puts
     SPICE on loopback or on a UNIX socket, and the domain XML guard
     (tools/guest_xml_contract.py) accepts it.
  2. The guard refuses a live domain that exposes a display server, whatever
     else matches: a VNC device added next to SPICE, SPICE on a libvirt
     network's address or on every address, a listen with no address, and
     a graphics type HyperLab does not use
     (problems/domain-xml-guard-missed-exposed-graphics.md).
  3. Every ready Template, on every network and device capability it
     offers, projects a VM spec with the SPICE clipboard off, and no
     Template file can carry a clipboard setting of its own.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

import guest_contract  # noqa: E402
from hyperlabctl.machine_factory import project_vm_spec, template_catalog  # noqa: E402

GUARD = ROOT / "tools/guest_xml_contract.py"
# The managed SPICE device's opening tag and listen, as the template renders it.
SPICE_LOOPBACK = re.compile(
    r'<graphics type="spice" autoport="yes" listen="127\.0\.0\.1">\s*<listen type="address" address="127\.0\.0\.1"/>')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rendered_domains() -> dict[str, str]:
    env = guest_contract.template_env()
    domains = {}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = guest_contract.standard_fixture(root)
        plan = guest_contract.build_plan(root, spec, store)
        domains["standard"] = env.get_template("domain.xml.j2").render(
            guest_plan=plan, guest_resolved_memory_mb=2048, guest_vfio={})
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store, report, profiles, trust = guest_contract.vfio_fixture(root)
        plan = guest_contract.build_plan(root, spec, store)
        result = guest_contract.build_vfio_plan(plan, report, profiles, trust)
        require(result.returncode == 0, result.stderr)
        looking = yaml.safe_load((ROOT / "group_vars/all/looking-glass.yml").read_text())
        domains["vfio"] = env.get_template("domain.xml.j2").render(
            guest_plan=plan, guest_resolved_memory_mb=6144,
            guest_vfio=json.loads(result.stdout),
            hyperlab_looking_glass_spice_socket_dir=looking["hyperlab_looking_glass_spice_socket_dir"])
    return domains


def guard(expected: str, actual: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "expected.xml").write_text(expected)
        (Path(td) / "actual.xml").write_text(actual)
        return subprocess.run(
            [sys.executable, str(GUARD), "--expected", f"{td}/expected.xml", "--actual", f"{td}/actual.xml"],
            capture_output=True, text=True, check=False)


def mutate(xml: str, old: str | re.Pattern, new: str) -> str:
    if isinstance(old, re.Pattern):
        found = old.findall(xml)
        require(len(found) == 1, f"fixture text not found once: {old.pattern!r}")
        old = found[0]
    require(xml.count(old) == 1, f"fixture text not found once: {old!r}")
    return xml.replace(old, new)


def check_rendered(domains: dict[str, str]) -> None:
    require(SPICE_LOOPBACK.search(domains["standard"]) is not None, "a standard Machine's SPICE is not on loopback")
    require('<listen type="socket" socket="' in domains["vfio"], "a VFIO Machine's SPICE is not on a socket")
    for name, xml in domains.items():
        result = guard(xml, xml)
        require(result.returncode == 0, f"the guard refused the rendered {name} domain: {result.stderr}")


def check_exposure(domains: dict[str, str]) -> None:
    xml = domains["standard"]
    vnc = '<graphics type="vnc" port="5900" autoport="no" listen="0.0.0.0"><listen type="address" address="0.0.0.0"/></graphics>'
    exposed = {
        "a VNC device on every address": mutate(xml, "</devices>", f"  {vnc}\n  </devices>"),
        "a second SPICE device on loopback": mutate(
            xml, "</devices>", '  <graphics type="spice" autoport="yes" listen="127.0.0.1"/>\n  </devices>'),
        "SPICE on a libvirt network": mutate(
            xml, SPICE_LOOPBACK, '<graphics type="spice" autoport="yes">\n      <listen type="network" network="dev"/>'),
        "SPICE on every address": mutate(
            xml, SPICE_LOOPBACK, '<graphics type="spice" autoport="yes" listen="0.0.0.0">\n      <listen type="address" address="0.0.0.0"/>'),
        "SPICE on every IPv6 address": mutate(
            xml, SPICE_LOOPBACK, '<graphics type="spice" autoport="yes" listen="::">\n      <listen type="address" address="::"/>'),
        "SPICE with a listen that names no address": mutate(
            xml, SPICE_LOOPBACK, '<graphics type="spice" autoport="yes">\n      <listen type="address"/>'),
        "SPICE with no listen at all": mutate(
            xml, SPICE_LOOPBACK, '<graphics type="spice" autoport="yes">'),
        "an RDP display": mutate(xml, "</devices>", '  <graphics type="rdp" autoport="yes"/>\n  </devices>'),
    }
    for label, actual in exposed.items():
        result = guard(xml, actual)
        require(result.returncode == 1, f"the guard accepted {label}: {result.stdout}{result.stderr}")
    for label in ("a VNC device on every address", "SPICE on a libvirt network", "SPICE on every address"):
        result = guard(xml, exposed[label])
        require("beyond loopback" in result.stderr, f"{label} was refused, but not as an exposure: {result.stderr}")
    ipv6 = mutate(xml, SPICE_LOOPBACK, '<graphics type="spice" autoport="yes" listen="::1">\n      <listen type="address" address="::1"/>')
    result = guard(ipv6, ipv6)
    require(result.returncode == 0, f"SPICE on IPv6 loopback was refused: {result.stderr}")


def check_clipboard() -> None:
    projected = 0
    for entry in template_catalog(ROOT):
        source = yaml.safe_load((ROOT / entry["source"]).read_text())
        require("clipboard" not in yaml.safe_dump(source), f"{entry['source']} carries a clipboard setting")
        if not entry["ready"]:
            continue
        image = yaml.safe_load((ROOT / f"images/{entry['image']['id']}.yml").read_text())
        for network in entry["network_profiles"]:
            for device in entry["device_capabilities"]:
                record = {
                    "schema_version": 1, "id": "clipboard-probe-01", "display_name": "Clipboard probe",
                    "template": {"id": entry["id"], "version": entry["version"]},
                    "image": {"id": image["id"], "sha256": image["sha256"]},
                    "lifecycle": entry["defaults"]["lifecycle"], "device_capability": device,
                    "gpu_handoff_profile": entry["defaults"]["gpu_handoff_profile"] if device == "vfio" else None,
                    "network_profile": network,
                    "resources": {"memory_mb": 8192, "vcpus": 4, "disk_gib": 200},
                    "presentation": dict(entry["presentation"]), "owner": "contract",
                    "created_at": "2026-10-05T12:00:00Z", "purpose": "clipboard default probe",
                }
                spec = project_vm_spec(ROOT, record)
                require(spec["clipboard"] is False,
                        f"{entry['id']} on {network}/{device} projects the SPICE clipboard on")
                projected += 1
    require(projected > 0, "no ready Template was projected")


def main() -> int:
    domains = rendered_domains()
    check_rendered(domains)
    check_exposure(domains)
    check_clipboard()
    print("Graphics exposure and clipboard default contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
