import json

from .. import document as doc
from ..render import paint
from .base import Command


class ImageCommand(Command):
    name = "image"
    help = "the declared image manifests"
    order = 28

    def configure(self, parser):
        sub = parser.add_subparsers(dest="image_action", required=True)
        sub.add_parser("list")

    def run(self, args, ctx):
        built = doc.build(ctx, only={"images", "store"})
        images = built.get("images") or []
        if args.json:
            print(json.dumps(images, indent=2))
            return 0
        store = built.get("store") or {}
        if store:
            print("store %s  %s GiB free" % (store.get("root"), store.get("free_gib")))
        for image in images:
            colour = {"sealed": "ok", "not-built": "dim"}.get(image["status"], "warn")
            print("  %-22s %-12s %6s  %s%s" % (
                image["name"], paint(image["status"], colour, args.color),
                "%s G" % image["virtual_size_gib"] if image["virtual_size_gib"] else "-",
                "sha256" if image["sha256"] else "no checksum",
                "  private" if image["private"] else ""))
        return 0
