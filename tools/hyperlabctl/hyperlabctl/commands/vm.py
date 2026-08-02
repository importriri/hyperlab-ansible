import json

from .. import document as doc
from ..inventory import domain_detail
from .base import Command


class VmCommand(Command):
    name = "vm"
    help = "list, inspect and move domains"
    order = 15

    def configure(self, parser):
        sub = parser.add_subparsers(dest="vm_action", required=True)
        sub.add_parser("list", help="every domain with state and allocation")
        for action in ("start", "stop", "inspect"):
            child = sub.add_parser(action)
            child.add_argument("domain")

    def run(self, args, ctx):
        if args.vm_action == "list":
            return self._list(args, ctx)
        if args.vm_action == "inspect":
            return self._inspect(args, ctx)
        return self._move(args, ctx)

    def _list(self, args, ctx):
        document = doc.build(ctx, only={"domains", "memory", "host"})
        domains = document.get("domains") or []
        if args.json:
            print(json.dumps(domains, indent=2))
            return 0
        for domain in domains:
            note = ""
            if domain["blocked"]:
                note = "  blocked: short %d MB" % domain["blocked"]["short_mb"]
            print("%-26s %-10s %8s %s%s" % (
                domain["name"], domain["state"],
                "%s MB" % domain["memory_mb"] if domain["memory_mb"] else "-",
                domain["network"] or "-", note))
        return 0

    def _inspect(self, args, ctx):
        detail = domain_detail(ctx, args.domain)
        if args.json:
            print(json.dumps(detail, indent=2))
        else:
            for key in ("name", "state", "memory_mb", "networks", "hostdevs", "vfio"):
                print("%-12s %s" % (key, detail[key]))
        return 0

    def _move(self, args, ctx):
        """start and stop stay unprivileged: the libvirt group already allows
        them. The refusal lives in operations.py so the panel refuses the same
        way, with the same numbers."""
        from ..operations import start, stop
        outcome = start(ctx, args.domain) if args.vm_action == "start" else stop(ctx, args.domain)
        print(outcome.message)
        return 0 if outcome.ok else 2
