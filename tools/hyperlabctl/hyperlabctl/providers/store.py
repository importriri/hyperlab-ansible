"""Free space under the image store against the threshold the manifests imply.

The threshold is derived, not typed: the largest declared virtual size times
one and a half. Adding a bigger image raises the bar by itself.
"""

import os
from pathlib import Path

from ..config import load_yaml
from ..errors import Unavailable
from .base import Provider

HEADROOM = 1.5


class StoreProvider(Provider):
    key = "store"
    order = 70
    summary = "image store capacity and how many manifests are unsealed"

    def collect(self, ctx):
        root = Path(ctx.config.var("hyperlab_root"))
        try:
            stat = os.statvfs(root)
        except OSError as exc:
            raise Unavailable("%s is not reachable: %s" % (root, exc)) from exc
        free_gib = round(stat.f_bavail * stat.f_frsize / (1024 ** 3), 1)

        largest, unsealed, total = 0, 0, 0
        manifests = ctx.config.repo_root / "images" if ctx.config.repo_root else None
        if manifests and manifests.is_dir():
            for item in sorted(manifests.glob("*.yml")):
                data = load_yaml(item) or {}
                total += 1
                largest = max(largest, int(data.get("virtual_size_gib") or 0))
                if data.get("status") != "sealed":
                    unsealed += 1
        threshold = round(largest * HEADROOM) if largest else None
        return {
            "root": str(root),
            "free_gib": free_gib,
            "threshold_gib": threshold,
            "manifests": total,
            "unsealed": unsealed,
        }

    def problems(self, ctx, section):
        if not section or section.get("threshold_gib") is None:
            return []
        if section["free_gib"] < section["threshold_gib"]:
            return [{
                "id": "store.low_space",
                "severity": "warn",
                "message": "%s GiB free, below the %s GiB the largest image implies"
                           % (section["free_gib"], section["threshold_gib"]),
            }]
        return []
