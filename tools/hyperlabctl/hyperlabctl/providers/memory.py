"""ADR 0007 read at runtime.

The budget is memtotal minus the reservations minus what is actually running,
never a cached number. A VFIO domain pins its whole allocation, so its overhead
is counted separately and overcommit is not applied to it.
"""

from ..errors import ContractError, Unavailable
from ..inventory import running
from .base import Provider


def _memtotal_mb(ctx):
    text = ctx.read_text(ctx.config.proc_meminfo)
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) // 1024
    raise Unavailable("MemTotal missing from %s" % ctx.config.proc_meminfo)


def budget(ctx):
    """Returned as data so the vm commands and the panel share one calculation."""
    profiles = ctx.config.var("host_profiles", {}) or {}
    from .host import HostProvider
    profile_name = HostProvider().collect(ctx).get("profile")
    profile = profiles.get(profile_name) or {}
    settings = profile.get("memory") or {}
    if not settings:
        raise Unavailable("no memory budget for profile %r" % profile_name)
    for required in ("host_reserved_mb", "qemu_overhead_per_domain_mb",
                     "services_reserved_mb", "vfio_fixed_overhead_mb"):
        if required not in settings:
            raise ContractError("host_profiles.%s.memory lacks %s" % (profile_name, required))

    total = _memtotal_mb(ctx)
    live = running(ctx)
    committed = sum(domain["memory_mb"] or 0 for domain in live)
    overhead = settings["qemu_overhead_per_domain_mb"] * len(live)
    overhead += settings["vfio_fixed_overhead_mb"] * len([d for d in live if d["vfio"]])
    assignable = (total
                  - settings["host_reserved_mb"]
                  - settings["services_reserved_mb"]
                  - committed
                  - overhead)
    return {
        "total_mb": total,
        "host_reserved_mb": settings["host_reserved_mb"],
        "services_reserved_mb": settings["services_reserved_mb"],
        "overhead_mb": overhead,
        "committed_mb": committed,
        "assignable_mb": max(assignable, 0),
        "negative": assignable < 0,
        "max_auto_memory_mb": settings.get("max_auto_memory_mb"),
        "running_domains": len(live),
    }


class MemoryProvider(Provider):
    key = "memory"
    order = 30
    summary = "assignable RAM for the next guest, per ADR 0007"

    def collect(self, ctx):
        return budget(ctx)

    def problems(self, ctx, section):
        if section and section.get("negative"):
            return [{
                "id": "memory.overcommitted",
                "severity": "error",
                "message": "running domains already exceed the budget: the next "
                           "hostdev start is an OOM kill",
            }]
        return []
