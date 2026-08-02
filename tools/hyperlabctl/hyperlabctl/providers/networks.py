"""The five security domains, compared against what libvirt actually has."""

from ..inventory import network_names
from .base import Provider


class NetworkProvider(Provider):
    key = "networks"
    order = 50
    summary = "declared security domains versus live libvirt networks"

    def collect(self, ctx):
        declared = [entry["name"] for entry in ctx.config.var("network_domains", []) or []]
        defined = set(network_names(ctx))
        active = set(network_names(ctx, active_only=True))
        return {
            "expected": len(declared),
            "active": len([name for name in declared if name in active]),
            "declared": declared,
            "missing": [name for name in declared if name not in defined],
            "inactive": [name for name in declared if name in defined and name not in active],
            "undeclared": sorted(defined - set(declared)),
        }

    def problems(self, ctx, section):
        found = []
        if section and section["missing"]:
            found.append({
                "id": "networks.missing",
                "severity": "error",
                "message": "declared but not defined: %s" % ", ".join(section["missing"]),
            })
        if section and section["inactive"]:
            found.append({
                "id": "networks.inactive",
                "severity": "warn",
                "message": "defined but down: %s" % ", ".join(section["inactive"]),
            })
        return found
