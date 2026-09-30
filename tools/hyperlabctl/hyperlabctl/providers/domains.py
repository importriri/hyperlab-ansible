"""Every domain, and for the stopped ones the reason they cannot start.

`blocked` is the point of this provider. A VM manager tells you a domain is off;
this tells you it is off and short 1.9 GB, which is the difference between a
panel and a list.
"""

from ..errors import Unavailable
from ..inventory import domains as all_domains
from .base import Provider


def network_identity(domain, declared):
    """The network trust identity of a HyperLab-managed guest, or None.

    The reviewed guest role writes `network-profile` from the guest's spec
    into the libvirt metadata. It is believed only for a managed domain whose
    every interface is attached to exactly that declared network, so neither
    a stale record nor an unreadable domain can invent an identity.
    """
    if domain.get("managed") is not True:
        return None
    profile = domain.get("network_profile")
    networks = domain.get("networks")
    if profile not in declared or not networks:
        return None
    if any(network != profile for network in networks):
        return None
    return profile


def resolve_trust(domain, gpu_profiles, declared):
    """(trust_profile, trust_source) from two separate authorities.

    Network identity classifies a managed guest. gpu_domain_profiles is the
    VFIO trust gate the handoff hook enforces; it names an unmanaged domain
    only because nothing else does. When both speak and disagree there is
    no identity, never a pick of one.
    """
    gpu = gpu_profiles.get(domain["name"])
    network = network_identity(domain, declared)
    if network is not None:
        if gpu is not None and gpu != network:
            return None, None
        return network, "network-profile"
    if domain.get("managed") is False and gpu is not None:
        return gpu, "gpu-domain-profile"
    return None, None


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
        declared = {entry.get("name") for entry in
                    ctx.config.var("network_domains", []) or []
                    if isinstance(entry, dict)}
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
            trust, source = resolve_trust(domain, profiles, declared)
            listed.append({
                "name": domain["name"],
                "state": domain["state"],
                "memory_mb": wanted,
                "network": domain["networks"][0] if domain["networks"] else None,
                "networks": domain["networks"],
                "vcpus": domain.get("vcpus"),
                "vfio": domain["vfio"],
                "managed": domain.get("managed"),
                "device_profile": domain.get("device_profile"),
                "lifecycle": domain.get("lifecycle"),
                "network_profile": domain.get("network_profile"),
                "gpu_trust_profile": profiles.get(domain["name"]),
                "trust_profile": trust,
                "trust_source": source,
                "blocked": blocked,
            })
        return listed

    def problems(self, ctx, section):
        found = []
        for domain in section or []:
            gpu = domain.get("gpu_trust_profile")
            network = domain.get("network_profile")
            if domain["vfio"] and gpu is None:
                found.append({
                    "id": "domains.unguarded_vfio",
                    "severity": "error",
                    "message": "%s owns a hostdev but is absent from "
                               "gpu_domain_profiles: the trust hook cannot guard it"
                               % domain["name"],
                })
            if not domain.get("managed"):
                continue
            if domain.get("trust_source") is None and network is not None:
                if gpu is not None and gpu != network:
                    found.append({
                        "id": "domains.trust_conflict",
                        "severity": "error",
                        "message": "%s is managed on network %s but "
                                   "gpu_domain_profiles names it %s"
                                   % (domain["name"], network, gpu),
                    })
                else:
                    found.append({
                        "id": "domains.network_identity_mismatch",
                        "severity": "warn",
                        "message": "%s declares network %s but is attached to %s"
                                   % (domain["name"], network,
                                      ", ".join(domain.get("networks") or [])
                                      or "no known network"),
                    })
        return found
