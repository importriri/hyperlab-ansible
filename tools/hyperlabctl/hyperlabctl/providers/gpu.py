"""Which driver holds the passthrough GPU, and which domain has it.

Read from sysfs rather than lspci: no parsing of human output, and the sysfs
root is injectable so the whole provider is testable from a fixture tree.
"""

from pathlib import Path

from ..errors import Unavailable
from ..inventory import running
from .base import Provider


def _devices_by_id(root, wanted):
    found = {}
    base = Path(root)
    if not base.is_dir():
        raise Unavailable("%s is not a directory" % root)
    for entry in sorted(base.iterdir()):
        try:
            vendor = (entry / "vendor").read_text().strip()
            device = (entry / "device").read_text().strip()
        except OSError:
            continue
        pci_id = "%s:%s" % (vendor.replace("0x", ""), device.replace("0x", ""))
        if pci_id not in wanted:
            continue
        driver = None
        link = entry / "driver"
        if link.is_symlink() or link.exists():
            driver = Path(link.resolve()).name
        found[entry.name] = {"id": pci_id, "driver": driver}
    return found


class GpuProvider(Provider):
    key = "gpu"
    order = 40
    summary = "passthrough GPU binding and current owner"

    def collect(self, ctx):
        from .host import HostProvider
        profile_name = HostProvider().collect(ctx).get("profile")
        profiles = ctx.config.var("host_profiles", {}) or {}
        wanted = ((profiles.get(profile_name) or {}).get("vfio_ids")) or []
        if not wanted:
            raise Unavailable("profile %r declares no vfio_ids" % profile_name)

        devices = _devices_by_id(ctx.config.sysfs_pci, set(wanted))
        drivers = sorted({info["driver"] for info in devices.values()})
        held_by = None
        addresses = set(devices)
        for domain in running(ctx):
            if addresses & set(domain["hostdevs"]):
                held_by = domain["name"]
                break
        return {
            "ids": list(wanted),
            "devices": devices,
            "driver": drivers[0] if len(drivers) == 1 else None,
            "drivers": drivers,
            "bound": all(info["driver"] == "vfio-pci" for info in devices.values()) and bool(devices),
            "held_by": held_by,
        }

    def problems(self, ctx, section):
        if not section:
            return []
        missing = set(section["ids"]) - {info["id"] for info in section["devices"].values()}
        if missing:
            return [{
                "id": "gpu.id_absent",
                "severity": "error",
                "message": "profile declares %s but no PCI device carries it"
                           % ", ".join(sorted(missing)),
            }]
        if not section["bound"]:
            return [{
                "id": "gpu.not_bound",
                "severity": "warn",
                "message": "GPU functions are on %s, not vfio-pci: this is not the "
                           "Vfio boot entry" % (", ".join(d or "none" for d in section["drivers"])),
            }]
        return []
