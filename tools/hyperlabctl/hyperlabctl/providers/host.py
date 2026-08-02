"""Which laptop this is. Read from the file hardware_probe writes, never probed.

group_vars says so in as many words: a brick that must know which machine this
is but has no business probing PCI reads the report. The cockpit is that brick.
"""

from ..config import load_yaml
from ..errors import Unavailable
from .base import Provider


class HostProvider(Provider):
    key = "host"
    order = 10
    summary = "selected hardware profile and hostname"

    def collect(self, ctx):
        profile = None
        try:
            report = load_yaml(ctx.config.hardware_profile_report) or {}
            profile = report.get("host_profile") or report.get("profile")
        except Unavailable:
            report = {}
        if not profile:
            declared = ctx.config.var("host_profile", "auto")
            profile = None if declared == "auto" else declared
        profiles = ctx.config.var("host_profiles", {}) or {}
        label = (profiles.get(profile) or {}).get("label") if profile else None
        return {
            "profile": profile,
            "label": label,
            "hostname": ctx.config.hostname(),
            "source": "report" if report else "group_vars",
        }

    def problems(self, ctx, section):
        if section and section.get("profile") is None:
            return [{
                "id": "host.profile_unknown",
                "severity": "warn",
                "message": "no hardware profile selected: run playbooks/preflight.yml",
            }]
        return []
