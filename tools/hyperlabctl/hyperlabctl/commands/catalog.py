import json

from ..composer import catalog
from .base import Command


class CatalogCommand(Command):
    name = "catalog"
    help = "show the VM creation matrix derived from image manifests"
    order = 18

    def configure(self, parser):
        parser.add_argument("--ready", action="store_true")
        parser.add_argument("--image", metavar="ID")

    def run(self, args, ctx):
        entries = catalog(ctx.config.repo_root)
        if args.ready:
            entries = [entry for entry in entries if entry["ready"]]
        if args.image:
            entries = [entry for entry in entries if entry["id"] == args.image]
        if args.json:
            print(json.dumps(entries, indent=2))
            return 0
        for entry in entries:
            state = "ready" if entry["ready"] else "blocked"
            print("%-13s %-22s %-9s %-13s %s" % (
                entry["id"],
                entry["display_name"],
                entry["os_family"],
                "/".join(entry["device_profiles"]),
                state,
            ))
            for device in entry["device_profiles"]:
                print("  %-8s lifecycle=%s networks=%s" % (
                    device,
                    ",".join(entry["lifecycles"]),
                    ",".join(entry["network_profiles_by_device"][device]),
                ))
            if entry["blocked_reason"]:
                print("           reason=%s" % entry["blocked_reason"])
        return 0
