import json

from .. import document as doc
from ..errors import Unavailable
from ..render import paint
from .base import Command


class NetCommand(Command):
    name = "net"
    help = "the security domains, and moving them"
    order = 25

    def configure(self, parser):
        sub = parser.add_subparsers(dest="net_action", required=True)
        sub.add_parser("list", help="declared versus live")
        for action in ("start", "stop"):
            child = sub.add_parser(action)
            child.add_argument("network")

    def run(self, args, ctx):
        if args.net_action == "list":
            return self._list(args, ctx)
        return self._move(args, ctx)

    def _list(self, args, ctx):
        built = doc.build(ctx, only={"networks", "host"})
        section = built.get("networks")
        if section is None:
            raise Unavailable("libvirt did not answer")
        declared = ctx.config.var("network_domains", []) or []
        trust = ctx.config.var("gpu_trust_levels", {}) or {}
        rows = []
        for entry in declared:
            name = entry["name"]
            state = ("missing" if name in section["missing"]
                     else "inactive" if name in section["inactive"] else "active")
            rows.append({"name": name, "state": state, "subnet": entry.get("subnet"),
                         "forward": entry.get("forward"), "trust": trust.get(name)})
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        for row in rows:
            colour = {"active": "ok", "inactive": "warn", "missing": "error"}[row["state"]]
            print("%-12s %-9s %-16s %-9s %s" % (
                row["name"], paint(row["state"], colour, args.color),
                row["subnet"] or "-", row["forward"] or "-",
                "trust %s" % row["trust"] if row["trust"] is not None else ""))
        return 0 if not section["missing"] else 2

    def _move(self, args, ctx):
        verb = "net-start" if args.net_action == "start" else "net-destroy"
        result = ctx.virsh(verb, args.network)
        if not result.ok:
            print(result.stderr.strip() or "virsh %s failed" % verb)
            return 2
        print(result.stdout.strip() or "%s: ok" % args.network)
        return 0
