"""The image manifests, as the store sees them.

Separate from the store section on purpose: the store is about the volume,
this is about what the volume is meant to hold. A manifest that claims sealed
without a checksum is a contract violation, not a warning.
"""

from ..config import load_yaml
from ..errors import Unavailable
from .base import Provider


class ImageProvider(Provider):
    key = "images"
    order = 65
    summary = "declared image manifests and their sealing state"

    def collect(self, ctx):
        if ctx.config.repo_root is None:
            raise Unavailable("no repository checkout: image manifests are in the repo")
        directory = ctx.config.repo_root / "images"
        if not directory.is_dir():
            raise Unavailable("%s does not exist" % directory)
        listed = []
        for item in sorted(directory.glob("*.yml")):
            data = load_yaml(item) or {}
            listed.append({
                "name": data.get("name") or item.stem,
                "status": data.get("status") or "unknown",
                "virtual_size_gib": data.get("virtual_size_gib"),
                "sha256": bool(data.get("sha256")),
                "private": bool(data.get("private")),
                "source": bool(data.get("source_url") or data.get("local_source")),
            })
        if not listed:
            raise Unavailable("no image manifests under %s" % directory)
        return listed

    def problems(self, ctx, section):
        found = []
        for image in section or []:
            if image["status"] == "sealed" and not image["sha256"]:
                found.append({
                    "id": "images.sealed_without_checksum",
                    "severity": "error",
                    "message": "%s claims sealed with no sha256: sealing requires both"
                               % image["name"],
                })
            if image["status"] == "not-built" and not image["source"]:
                found.append({
                    "id": "images.no_source",
                    "severity": "warn",
                    "message": "%s has no source recorded yet" % image["name"],
                })
        return found
