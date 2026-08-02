"""A whole fake host in a temp directory: repo, sysfs, proc, run state, virsh."""

import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyperlabctl.config import Config, Context
from hyperlabctl.runner import RecordedRunner

GROUP_VARS = {
    "identity.yml": """---
admin_user: sid
host_hostname: hypervisor-01
""",
    "hardware.yml": """---
host_profile: auto
host_profiles:
  nitro-3060:
    label: Acer Nitro 5 / RTX 3060 Mobile
    vfio_ids:
      - "10de:2520"
      - "10de:228e"
    memory:
      host_reserved_mb: 2048
      qemu_overhead_per_domain_mb: 512
      services_reserved_mb: 0
      vfio_fixed_overhead_mb: 256
      max_auto_memory_mb: 6144
""",
    "networks.yml": """---
network_domains:
  - name: clean
  - name: dirty
  - name: dev
  - name: lab
  - name: services
gpu_trust_levels:
  clean: 3
  dev: 2
  dirty: 1
  lab: 0
gpu_domain_profiles:
  win11clean-valley: clean
""",
    "storage.yml": """---
hyperlab_root: HYPERLAB_ROOT
""",
}

DOMAIN_XML = """<domain type='kvm'>
  <name>{name}</name>
  <memory unit='KiB'>{kib}</memory>
  <devices>
    <interface type='network'><source network='{net}'/></interface>
    {hostdev}
  </devices>
</domain>"""

HOSTDEV = """<hostdev mode='subsystem' type='pci'>
      <source><address domain='0x0000' bus='0x01' slot='0x00' function='0x0'/></source>
    </hostdev>"""


def build(domains=None, trust=None, memtotal_kb=7948000, drivers=None,
          networks_active=None, profile_report=True, images=None):
    root = Path(tempfile.mkdtemp(prefix="hyperlab-test-"))
    repo = root / "repo"
    (repo / "group_vars" / "all").mkdir(parents=True)
    (repo / "roles").mkdir()
    (repo / "images").mkdir()
    store = root / "store"
    store.mkdir()
    for name, text in GROUP_VARS.items():
        (repo / "group_vars" / "all" / name).write_text(text.replace("HYPERLAB_ROOT", str(store)))
    (repo / "images" / "debian.yml").write_text("---\nvirtual_size_gib: 20\nstatus: not-built\n")
    for name, body in (images or {}).items():
        (repo / "images" / ("%s.yml" % name)).write_text(body)

    report = root / "hardware-profile.yml"
    if profile_report:
        report.write_text("---\nhost_profile: nitro-3060\n")

    meminfo = root / "meminfo"
    meminfo.write_text("MemTotal:       %d kB\nMemFree:  100 kB\n" % memtotal_kb)

    trust_file = root / "trust"
    if trust is not None:
        trust_file.write_text("%s\n" % trust)

    sysfs = root / "pci"
    sysfs.mkdir()
    drivers = drivers if drivers is not None else {"0000:01:00.0": "vfio-pci",
                                                   "0000:01:00.1": "vfio-pci"}
    ids = {"0000:01:00.0": ("0x10de", "0x2520"), "0000:01:00.1": ("0x10de", "0x228e")}
    for address, (vendor, device) in ids.items():
        entry = sysfs / address
        entry.mkdir()
        (entry / "vendor").write_text(vendor + "\n")
        (entry / "device").write_text(device + "\n")
        driver = drivers.get(address)
        if driver:
            target = root / "drivers" / driver
            target.mkdir(parents=True, exist_ok=True)
            (entry / "driver").symlink_to(target)

    domains = domains if domains is not None else []
    runner = RecordedRunner()
    virsh = ["/usr/bin/virsh", "-c", "qemu:///system", "-q"]
    runner.register(virsh + ["list", "--all", "--name"],
                    "\n".join(domain["name"] for domain in domains) + "\n")
    declared = ["clean", "dirty", "dev", "lab", "services"]
    active = declared if networks_active is None else networks_active
    runner.register(virsh + ["net-list", "--all", "--name"], "\n".join(declared) + "\n")
    runner.register(virsh + ["net-list", "--name"], "\n".join(active) + "\n")
    for heartbeat in ("60", "5"):
        runner.register(virsh + ["event", "--all", "--timeout", heartbeat], "")
    for domain in domains:
        runner.register(virsh + ["domstate", domain["name"]], domain["state"] + "\n")
        runner.register(virsh + ["dumpxml", domain["name"]], DOMAIN_XML.format(
            name=domain["name"], kib=domain["memory_mb"] * 1024,
            net=domain.get("network", "clean"),
            hostdev=HOSTDEV if domain.get("vfio") else ""))
        runner.register(virsh + ["start", domain["name"]], "Domain started\n")
        runner.register(virsh + ["shutdown", domain["name"]], "Domain is being shutdown\n")

    config = Config(repo_root=repo, overrides={
        "hardware_profile_report": str(report),
        "gpu_handoff_state": str(trust_file),
        "proc_meminfo": str(meminfo),
        "sysfs_pci": str(sysfs),
    })
    return Context(config, runner)
