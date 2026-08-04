"""Moving a domain. One implementation, two callers.

The CLI and the panel must refuse identically, so neither of them owns this:
a behaviour that exists in both is a bug in one of them (ADR 0004).
"""

from .errors import HyperlabError
from .inventory import domain_detail
from .providers.memory import budget

WAYBAR_SIGNAL = 8


class Outcome:
    __slots__ = ("ok", "message", "acted")

    def __init__(self, ok, message, acted=True):
        self.ok = ok
        self.message = message
        self.acted = acted


def refresh_bar(ctx):
    """Tell waybar the lab moved, best effort."""
    result = ctx.runner.run([ctx.config.pkill_bin,
                             "-RTMIN+%d" % WAYBAR_SIGNAL, "-x", "waybar"])
    return result.rc == 0


def _managed_refusal(detail, operation):
    if not detail.get("managed"):
        return None
    return Outcome(
        False,
        "refusing direct libvirt %s of managed domain %s: use the checked-in VM spec "
        "through the M3 lifecycle playbook" % (operation, detail["name"]),
        acted=False,
    )


def start(ctx, name):
    detail = domain_detail(ctx, name)
    managed = _managed_refusal(detail, "start")
    if managed:
        return managed
    if detail["state"] == "running":
        return Outcome(True, "%s is already running" % name, acted=False)
    if detail.get("vfio"):
        profiles = ctx.config.var("gpu_domain_profiles", {}) or {}
        if name not in profiles:
            return Outcome(False,
                           "refusing %s: VFIO domain is absent from gpu_domain_profiles" % name,
                           acted=False)
    try:
        available = budget(ctx)["assignable_mb"]
    except HyperlabError as exc:
        return Outcome(False,
                       "refusing %s: memory budget is unavailable (%s)"
                       % (name, exc), acted=False)
    wanted = detail["memory_mb"] or 0
    if wanted > available:
        return Outcome(False,
                       "refusing %s: wants %d MB, %d MB assignable (short %d)"
                       % (name, wanted, available, wanted - available),
                       acted=False)
    result = ctx.virsh("start", name)
    if not result.ok:
        return Outcome(False, result.stderr.strip() or "virsh start failed")
    refresh_bar(ctx)
    return Outcome(True, result.stdout.strip() or "%s started" % name)


def stop(ctx, name):
    detail = domain_detail(ctx, name)
    managed = _managed_refusal(detail, "shutdown")
    if managed:
        return managed
    if detail["state"] != "running":
        return Outcome(True, "%s is not running" % name, acted=False)
    result = ctx.virsh("shutdown", name)
    if not result.ok:
        return Outcome(False, result.stderr.strip() or "virsh shutdown failed")
    refresh_bar(ctx)
    return Outcome(True, result.stdout.strip() or "%s is shutting down" % name)
