"""Every domain, and for the stopped ones the reason they cannot start.

`blocked` is the point of this provider. A VM manager tells you a domain is off;
this tells you it is off and short 1.9 GB, which is the difference between a
panel and a list.
"""

from ..errors import Unavailable
from ..inventory import domains as all_domains
from .base import Provider


class DomainProvider(Provider):
    key = "domains"
    order = 60
    summary = "domains with state, allocation and why a stopped one is blocked"

    def collect(self, ctx):
        from .memory import budget
        try:
            available = budget(ctx)["assignable_mb"]
        except (Unavailable, KeyError):
            available = None

        profiles = ctx.config.var("gpu_domain_profiles", {}) or {}
        listed = []
        for domain in all_domains(ctx):
            running_now = domain["state"] == "running"
            blocked = None
            wanted = domain["memory_mb"]
            if not running_now and available is not None and wanted:
                if wanted > available:
                    blocked = {"reason": "memory",
                               "short_mb": wanted - available,
                               "available_mb": available}
            listed.append({
                "name": domain["name"],
                "state": domain["state"],
                "memory_mb": wanted,
                "network": domain["networks"][0] if domain["networks"] else None,
                "networks": domain["networks"],
                "vfio": domain["vfio"],
                "managed": domain.get("managed", False),
                "device_profile": domain.get("device_profile"),
                "lifecycle": domain.get("lifecycle"),
                "trust_profile": profiles.get(domain["name"]),
                "blocked": blocked,
            })
        return listed

    def problems(self, ctx, section):
        found = []
        for domain in section or []:
            if domain["vfio"] and domain["trust_profile"] is None:
                found.append({
                    "id": "domains.unguarded_vfio",
                    "severity": "error",
                    "message": "%s owns a hostdev but is absent from "
                               "gpu_domain_profiles: the trust hook cannot guard it"
                               % domain["name"],
                })
        return found
