"""hyperlabctl doctor --hardware: readiness and a profile proposal (ADR 0050)."""

import io
import json
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import yaml
from harness import check, equals
from hyperlabctl import hardware
from hyperlabctl.cli import main
from hyperlabctl.config import Config, Context
from hyperlabctl.runner import Runner

REPO = Path(__file__).resolve().parents[3]

# The Nitro as read on 2026-10-06: the Intel iGPU the firmware boots on, the
# RTX 3060 and its audio function behind a root port in group 2.
NITRO_PCI = {
    "0000:00:01.0": ("0x060400", "0x8086", "0x1901", "pcieport", 2, None),
    "0000:00:02.0": ("0x030000", "0x8086", "0x9bc4", "i915", 0, "1"),
    "0000:00:14.0": ("0x0c0330", "0x8086", "0x06ed", "xhci_hcd", 4, None),
    "0000:00:1f.3": ("0x040380", "0x8086", "0x06c8", "snd_hda_intel", 13, None),
    "0000:01:00.0": ("0x030000", "0x10de", "0x2520", "vfio-pci", 2, "0"),
    "0000:01:00.1": ("0x040300", "0x10de", "0x228e", "vfio-pci", 2, None),
}


def _tree(pci=None, flags="fpu vmx sse", iommu=True, memory_kb=32684968, tpm="2", secure_boot=1,
          siblings=("0,4", "1,5", "2,6", "3,7", "0,4", "1,5", "2,6", "3,7")):
    root = Path(tempfile.mkdtemp(prefix="hyperlab-hw-"))
    (root / "proc").mkdir()
    (root / "proc/cpuinfo").write_text("processor\t: 0\nflags\t\t: %s\n" % flags)
    (root / "proc/meminfo").write_text("MemTotal:       %d kB\n" % memory_kb)
    (root / "proc/cmdline").write_text("intel_iommu=on iommu=pt\n")
    (root / "dev").mkdir()
    (root / "dev/kvm").write_text("")
    (root / "etc").mkdir()
    (root / "etc/vconsole.conf").write_text("KEYMAP=us\n")
    efivars = root / "sys/firmware/efi/efivars"
    efivars.mkdir(parents=True)
    if secure_boot is not None:
        (efivars / "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c").write_bytes(bytes([6, 0, 0, 0, secure_boot]))
    if tpm:
        (root / "sys/class/tpm/tpm0").mkdir(parents=True)
        (root / "sys/class/tpm/tpm0/tpm_version_major").write_text(tpm + "\n")
    dmi = root / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    (dmi / "product_name").write_text("Nitro AN515-55\n")
    (dmi / "sys_vendor").write_text("Acer\n")
    for number, value in enumerate(siblings):
        topology = root / ("sys/devices/system/cpu/cpu%d/topology" % number)
        topology.mkdir(parents=True)
        (topology / "thread_siblings_list").write_text(value + "\n")
    groups = root / "sys/kernel/iommu_groups"
    groups.mkdir(parents=True)
    drivers = root / "sys/bus/pci/drivers"
    devices = root / "sys/bus/pci/devices"
    devices.mkdir(parents=True)
    for address, (klass, vendor, device, driver, group, boot_vga) in (pci or NITRO_PCI).items():
        entry = devices / address
        entry.mkdir()
        (entry / "class").write_text(klass + "\n")
        (entry / "vendor").write_text(vendor + "\n")
        (entry / "device").write_text(device + "\n")
        if boot_vga is not None:
            (entry / "boot_vga").write_text(boot_vga + "\n")
        (drivers / driver).mkdir(parents=True, exist_ok=True)
        os.symlink(drivers / driver, entry / "driver")
        if iommu:
            (groups / str(group) / "devices").mkdir(parents=True, exist_ok=True)
            os.symlink(groups / str(group), entry / "iommu_group")
    return root


def _cli(root, *argv):
    config = Config(repo_root=REPO, read_files=False)
    ctx = Context(config, Runner(), environ={"HYPERLAB_HARDWARE_ROOT": str(root)})
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(list(argv), ctx=ctx)
    return code, buffer.getvalue()


def _statuses(checks):
    return {item["id"]: item["status"] for item in checks}


def test_hardware_nitro_is_ready():
    code, output = _cli(_tree(), "--json", "doctor", "--hardware")
    equals("hw_nitro_exit", code, 0)
    statuses = _statuses(json.loads(output)["checks"])
    equals("hw_nitro_all_ok", {key for key, value in statuses.items() if value != "ok"}, set())
    for ident in ("cpu-virtualization", "kvm", "uefi", "iommu", "host-gpu", "gpu-passthrough", "memory", "tpm2",
                  "secure-boot"):
        check("hw_nitro_checked_%s" % ident, ident in statuses)


def test_hardware_profile_matches_the_reviewed_nitro_profile():
    code, output = _cli(_tree(), "doctor", "--hardware", "--profile", "nitro-3060")
    equals("hw_profile_exit", code, 0)
    check("hw_profile_says_review", output.startswith("# A host profile proposal"))
    proposal = yaml.safe_load(output)["nitro-3060"]
    reviewed = yaml.safe_load((REPO / "group_vars/all/hardware.yml").read_text())["host_profiles"]["nitro-3060"]
    equals("hw_profile_vfio_ids", proposal["vfio_ids"], reviewed["vfio_ids"])
    equals("hw_profile_threads", proposal["cpu_pinning"]["host_cpu_threads"],
           reviewed["cpu_pinning"]["host_cpu_threads"])
    for vcpus in ("4", "6"):
        equals("hw_profile_plan_%s" % vcpus, proposal["cpu_pinning"]["plans"][vcpus],
               reviewed["cpu_pinning"]["plans"][vcpus])
    equals("hw_profile_memory", proposal["memory"], reviewed["memory"])
    equals("hw_profile_label", proposal["label"], "Acer Nitro AN515-55")
    equals("hw_profile_keys", sorted(proposal), sorted(reviewed))
    check("hw_profile_evidence_null", proposal["gpu_pci"] is None and proposal["cpu_threads"] is None)


def test_hardware_shared_group_is_refused_not_split():
    pci = dict(NITRO_PCI)
    pci["0000:00:14.0"] = ("0x0c0330", "0x8086", "0x06ed", "xhci_hcd", 2, None)
    code, output = _cli(_tree(pci=pci), "--json", "doctor", "--hardware")
    checks = {item["id"]: item for item in json.loads(output)["checks"]}
    equals("hw_shared_status", checks["gpu-passthrough"]["status"], "warn")
    check("hw_shared_names_stranger", "0000:00:14.0" in checks["gpu-passthrough"]["message"])
    equals("hw_shared_exit", code, 0)
    code, output = _cli(_tree(pci=pci), "doctor", "--hardware", "--profile", "shared")
    equals("hw_shared_no_vfio_ids", yaml.safe_load(output)["shared"]["vfio_ids"], [])


def test_hardware_without_virtualization_or_iommu_fails():
    code, output = _cli(_tree(flags="fpu sse", iommu=False), "--json", "doctor", "--hardware")
    statuses = _statuses(json.loads(output)["checks"])
    equals("hw_bad_exit", code, 2)
    equals("hw_bad_virt", statuses["cpu-virtualization"], "fail")
    equals("hw_bad_iommu", statuses["iommu"], "fail")
    equals("hw_bad_gpu", statuses["gpu-passthrough"], "warn")


def test_hardware_small_or_unknown_machines_are_flagged():
    code, output = _cli(_tree(memory_kb=6 * 1024 * 1024, tpm=None, secure_boot=None), "--json", "doctor",
                        "--hardware")
    statuses = _statuses(json.loads(output)["checks"])
    equals("hw_small_memory", statuses["memory"], "fail")
    equals("hw_small_tpm", statuses["tpm2"], "warn")
    equals("hw_small_secure_boot", statuses["secure-boot"], "warn")
    equals("hw_small_exit", code, 2)


def test_hardware_pinning_without_smt_and_uneven_cores():
    plans = hardware.pinning_plans([(0,), (1,), (2,), (3,)])
    equals("hw_nosmt_counts", sorted(plans, key=int), ["1", "2", "3"])
    equals("hw_nosmt_three", plans["3"]["vcpu_pins"], [1, 2, 3])
    equals("hw_nosmt_shared_io", plans["3"]["iothread_cpus"], plans["3"]["emulator_cpus"])
    equals("hw_uneven_none", hardware.pinning_plans([(0, 4), (1,), (2, 6)]), {})
    equals("hw_one_core_none", hardware.pinning_plans([(0, 1)]), {})


def test_hardware_profile_arguments_are_checked():
    root = _tree()
    equals("hw_profile_without_hardware", _cli(root, "doctor", "--profile", "x1")[0], 2)
    equals("hw_profile_bad_name", _cli(root, "doctor", "--hardware", "--profile", "../etc")[0], 2)
