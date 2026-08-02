"""Shared libvirt reads. Cached on the context, so five providers cost one call."""

from .domainxml import parse_domain
from .errors import Unavailable


def _names(result, what):
    if result.rc == 127:
        raise Unavailable("virsh is not installed on this host")
    if not result.ok:
        raise Unavailable("virsh could not list %s: %s" % (what, result.stderr.strip()))
    return result.lines()


def domain_names(ctx):
    return _names(ctx.virsh("list", "--all", "--name"), "domains")


def network_names(ctx, active_only=False):
    args = ["net-list", "--name"] if active_only else ["net-list", "--all", "--name"]
    return _names(ctx.virsh(*args), "networks")


def domain_state(ctx, name):
    result = ctx.virsh("domstate", name)
    if not result.ok:
        return "unknown"
    return (result.stdout.strip() or "unknown").lower()


def domain_detail(ctx, name):
    result = ctx.virsh("dumpxml", name)
    if not result.ok:
        raise Unavailable("dumpxml failed for %s" % name)
    detail = parse_domain(result.stdout)
    detail["name"] = detail["name"] or name
    detail["state"] = domain_state(ctx, name)
    return detail


def domains(ctx):
    if "inventory.domains" not in ctx.cache:
        collected = []
        for name in domain_names(ctx):
            try:
                collected.append(domain_detail(ctx, name))
            except Unavailable:
                collected.append(
                    {"name": name, "state": "unknown", "memory_mb": None,
                     "networks": [], "hostdevs": [], "vfio": False,
                     "managed": False, "device_profile": None, "lifecycle": None}
                )
        ctx.cache["inventory.domains"] = collected
    return ctx.cache["inventory.domains"]


def running(ctx):
    return [domain for domain in domains(ctx) if domain["state"] == "running"]
