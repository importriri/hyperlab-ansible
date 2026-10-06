"""What this computer offers HyperLab, read without privilege (ADR 0050).

Everything here reads /proc and /sys under a root that tests replace with a
fixture tree. Nothing is written and nothing needs root: the readiness
checks run before HyperLab is installed, and the profile they propose is a
file the operator reviews, never one HyperLab trusts on its own.
"""

import re
from pathlib import Path

DISPLAY_CLASS = 0x03
BRIDGE_CLASS = 0x0604
GIB = 1024
PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def _read(path, default=None):
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _cpus(text):
    """'0,4' or '0-1' or '2-3,6-7' -> sorted ints."""
    found = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            found.update(range(int(low), int(high) + 1))
        else:
            found.add(int(part))
    return sorted(found)


def _hex(text):
    try:
        return int(text, 16)
    except (TypeError, ValueError):
        return None


def pci_devices(root):
    base = root / "sys/bus/pci/devices"
    devices = {}
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return devices
    for entry in entries:
        group_link = entry / "iommu_group"
        driver_link = entry / "driver"
        devices[entry.name] = {
            "address": entry.name,
            "class": _hex(_read(entry / "class")),
            "vendor": _read(entry / "vendor", "")[2:],
            "device": _read(entry / "device", "")[2:],
            "driver": driver_link.resolve().name if driver_link.exists() else None,
            "iommu_group": group_link.resolve().name if group_link.exists() else None,
            "boot_vga": _read(entry / "boot_vga") == "1",
        }
    return devices


def cpu_cores(root):
    """Physical cores as sorted thread lists, from the kernel's sibling lists."""
    base = root / "sys/devices/system/cpu"
    cores = set()
    try:
        entries = list(base.glob("cpu[0-9]*"))
    except OSError:
        entries = []
    for entry in entries:
        siblings = _read(entry / "topology/thread_siblings_list")
        if siblings:
            cores.add(tuple(_cpus(siblings)))
    return sorted(cores)


def read_host(root=Path("/")):
    root = Path(root)
    cpuinfo = _read(root / "proc/cpuinfo", "")
    flags = set()
    for line in cpuinfo.splitlines():
        if line.startswith("flags"):
            flags.update(line.split(":", 1)[1].split())
            break
    meminfo = _read(root / "proc/meminfo", "")
    match = re.search(r"^MemTotal:\s+(\d+) kB", meminfo, re.M)
    groups_dir = root / "sys/kernel/iommu_groups"
    try:
        groups = len(list(groups_dir.iterdir()))
    except OSError:
        groups = 0
    secure_boot = None
    efivars = root / "sys/firmware/efi/efivars"
    try:
        for entry in efivars.glob("SecureBoot-*"):
            data = entry.read_bytes()
            secure_boot = bool(data[-1]) if data else None
            break
    except OSError:
        pass
    lockdown = _read(root / "sys/kernel/security/lockdown")
    if lockdown:
        chosen = re.search(r"\[(\w+)\]", lockdown)
        lockdown = chosen.group(1) if chosen else None
    return {
        "virtualization": "vmx" if "vmx" in flags else "svm" if "svm" in flags else None,
        "kvm_device": (root / "dev/kvm").exists(),
        "iommu_groups": groups,
        "cmdline": (_read(root / "proc/cmdline", "") or "").split(),
        "uefi": (root / "sys/firmware/efi").is_dir(),
        "secure_boot": secure_boot,
        "tpm_version": _read(root / "sys/class/tpm/tpm0/tpm_version_major"),
        "memory_mb": int(match.group(1)) // 1024 if match else None,
        "lockdown": lockdown,
        "cores": cpu_cores(root),
        "pci": pci_devices(root),
        "product": _read(root / "sys/class/dmi/id/product_name"),
        "vendor": _read(root / "sys/class/dmi/id/sys_vendor"),
        "keymap": _keymap(_read(root / "etc/vconsole.conf", "")),
    }


def _keymap(text):
    match = re.search(r"^KEYMAP=([A-Za-z0-9_-]+)\s*$", text or "", re.M)
    return match.group(1) if match else None


def _slot(address):
    return address.rsplit(".", 1)[0]


def displays(facts):
    return [d for d in facts["pci"].values() if d["class"] is not None and d["class"] >> 16 == DISPLAY_CLASS]


def passthrough_candidate(facts):
    """The display device a Machine could take, and why it can or cannot.

    The candidate is a display device that is not the one the firmware
    booted on. Its IOMMU group may hold only its own functions and PCI
    bridges: HyperLab never uses the ACS override, so a shared group is a
    refusal, not a workaround.
    """
    candidates = [d for d in displays(facts) if not d["boot_vga"]]
    if not candidates:
        return None, "no display device besides the one the host boots on"
    if len(candidates) > 1:
        return None, "more than one display device could be passed through: %s" % ", ".join(
            d["address"] for d in candidates)
    gpu = candidates[0]
    if gpu["iommu_group"] is None:
        return None, "%s is in no IOMMU group" % gpu["address"]
    members = [d for d in facts["pci"].values() if d["iommu_group"] == gpu["iommu_group"]]
    functions = [d for d in members if _slot(d["address"]) == _slot(gpu["address"])]
    strangers = [d for d in members if d not in functions and d["class"] != BRIDGE_CLASS
                 and (d["class"] or 0) >> 8 != BRIDGE_CLASS]
    if strangers:
        return None, "IOMMU group %s also holds %s; HyperLab does not split groups" % (
            gpu["iommu_group"], ", ".join(d["address"] for d in strangers))
    return {"gpu": gpu, "functions": sorted(functions, key=lambda d: d["address"])}, None


def check(status, ident, message, fix=None):
    return {"status": status, "id": ident, "message": message, "fix": fix}


def assess(facts):
    """Readiness checks, each ok, warn or fail, with what would clear it."""
    checks = []
    if facts["virtualization"]:
        checks.append(check("ok", "cpu-virtualization", "CPU virtualization: %s" % facts["virtualization"]))
    else:
        checks.append(check("fail", "cpu-virtualization", "the CPU offers no virtualization (vmx or svm)",
                            "turn on Intel VT-x or AMD-V in the firmware settings"))
    if facts["kvm_device"]:
        checks.append(check("ok", "kvm", "/dev/kvm is present"))
    else:
        checks.append(check("fail", "kvm", "/dev/kvm is missing", "load kvm_intel or kvm_amd"))
    if facts["uefi"]:
        checks.append(check("ok", "uefi", "booted with UEFI"))
    else:
        checks.append(check("fail", "uefi", "booted without UEFI; HyperLab installs only on UEFI",
                            "switch the firmware to UEFI boot"))
    if facts["iommu_groups"]:
        checks.append(check("ok", "iommu", "IOMMU on: %d groups" % facts["iommu_groups"]))
    else:
        checks.append(check("fail", "iommu", "no IOMMU groups: device passthrough is impossible",
                            "turn on VT-d or AMD-Vi in the firmware, and boot with intel_iommu=on "
                            "on Intel"))
    host_gpus = [d for d in displays(facts) if d["boot_vga"]]
    if host_gpus:
        checks.append(check("ok", "host-gpu", "the host keeps %s for its own screen" % host_gpus[0]["address"]))
    else:
        checks.append(check("warn", "host-gpu", "no display device is marked as the boot device",
                            "HyperLab does not pass the host's only GPU to a Machine"))
    candidate, why = passthrough_candidate(facts)
    if candidate:
        ids = ", ".join("%s:%s" % (d["vendor"], d["device"]) for d in candidate["functions"])
        checks.append(check("ok", "gpu-passthrough", "%s can be passed through alone (%s)"
                            % (candidate["gpu"]["address"], ids)))
    else:
        checks.append(check("warn", "gpu-passthrough", "no GPU to pass through: %s" % why,
                            "Machines still run, without a GPU of their own"))
    memory = facts["memory_mb"]
    if memory is None:
        checks.append(check("fail", "memory", "MemTotal could not be read"))
    elif memory < 8 * GIB:
        checks.append(check("fail", "memory", "%d MiB of memory; HyperLab needs at least 8 GiB" % memory))
    elif memory < 16 * GIB:
        checks.append(check("warn", "memory", "%d MiB of memory; a GPU Machine next to others needs 16 GiB"
                            % memory))
    else:
        checks.append(check("ok", "memory", "%d MiB of memory" % memory))
    if facts["tpm_version"] == "2":
        checks.append(check("ok", "tpm2", "TPM 2.0 present"))
    else:
        checks.append(check("warn", "tpm2", "no TPM 2.0: measured boot and TPM unlock are unavailable",
                            "turn on the firmware TPM (PTT or fTPM)"))
    if facts["secure_boot"] is True:
        checks.append(check("ok", "secure-boot", "Secure Boot is on"))
    elif facts["secure_boot"] is False:
        checks.append(check("warn", "secure-boot", "Secure Boot is off",
                            "HyperLab's measured boot enrolls its own keys later (ADR 0044)"))
    else:
        checks.append(check("warn", "secure-boot", "the Secure Boot state could not be read"))
    if not facts["cores"]:
        checks.append(check("warn", "cpu-topology", "the CPU topology could not be read; no pinning plan"))
    return checks


def pinning_plans(cores):
    """Pinning plans that keep each physical core's threads together.

    The first core runs the emulator. A plan that leaves a second core free
    gives it the I/O thread; otherwise the I/O thread shares the first. The
    guest takes whole cores from the top, and at least one core always stays
    with the host.
    """
    plans = {}
    if len(cores) < 2:
        return plans
    threads = len(cores[0])
    if any(len(core) != threads for core in cores):
        return plans
    for guest_cores in range(1, len(cores)):
        taken = cores[len(cores) - guest_cores:]
        free = cores[:len(cores) - guest_cores]
        emulator = list(free[0])
        iothread = list(free[1]) if len(free) > 1 else list(free[0])
        vcpus = guest_cores * threads
        plans[str(vcpus)] = {
            "vcpu_pins": [cpu for core in taken for cpu in core],
            "emulator_cpus": emulator,
            "iothread_cpus": iothread,
            "topology": {"sockets": 1, "dies": 1, "cores": guest_cores, "threads": threads},
        }
    return plans


def profile(facts, name):
    """A host profile proposal in the shape of group_vars/all/hardware.yml."""
    candidate, _why = passthrough_candidate(facts)
    memory = facts["memory_mb"] or 0
    label = " ".join(part for part in (facts["vendor"], facts["product"]) if part) or name
    return {
        name: {
            "label": label,
            "vfio_ids": ["%s:%s" % (d["vendor"], d["device"]) for d in candidate["functions"]] if candidate else [],
            "desktop": {
                "keyboard_layout": facts["keymap"] or "us",
                "keyboard_variant": "",
                "keyboard_options": "",
                "touchpad": {"dwt": "enabled", "middle_emulation": "enabled", "natural_scroll": "enabled",
                             "tap": "enabled"},
            },
            "memory": {
                "host_reserved_mb": 2048,
                "qemu_overhead_per_domain_mb": 512,
                "services_reserved_mb": 0,
                "vfio_fixed_overhead_mb": 256,
                # Half the memory, to the nearest GiB: the reviewed Nitro value.
                "max_auto_memory_mb": max(2048, round(memory / 2 / GIB) * GIB),
                "standard_overcommit_ratio": 1.0,
            },
            "gpu_pci": None,
            "gpu_audio_pci": None,
            "cpu_threads": None,
            "cpu_pinning": {
                "host_cpu_threads": sum(len(core) for core in facts["cores"]),
                "plans": pinning_plans(facts["cores"]),
            },
        }
    }
