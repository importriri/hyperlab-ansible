"""Where the GPU sits on the trust ladder inside this boot.

The hook writes one number to /run/gpu-handoff/trust. No file means the GPU was
never claimed since boot, which is the only state from which anything can rise.
"""

from ..errors import Unavailable
from .base import Provider


class TrustProvider(Provider):
    key = "trust"
    order = 20
    summary = "current GPU trust level and whether it can still rise"

    def collect(self, ctx):
        levels = ctx.config.var("gpu_trust_levels", {}) or {}
        try:
            raw = ctx.read_text(ctx.config.gpu_handoff_state).strip()
        except Unavailable:
            return {"level": None, "name": None, "claimed": False, "can_ascend": True,
                    "ladder": levels}
        try:
            level = int(raw)
        except ValueError as exc:
            raise Unavailable("trust state %r is not a number" % raw) from exc
        name = next((key for key, value in levels.items() if value == level), None)
        return {"level": level, "name": name, "claimed": True, "can_ascend": False,
                "ladder": levels}

    def problems(self, ctx, section):
        if section and section.get("claimed") and section.get("name") is None:
            return [{
                "id": "trust.level_unmapped",
                "severity": "error",
                "message": "trust level %s matches no entry in gpu_trust_levels"
                           % section["level"],
            }]
        return []
