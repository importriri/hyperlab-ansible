import json

from ..journal import read
from ..render import paint
from .base import Command


class LogsCommand(Command):
    name = "logs"
    help = "recent libvirt journal entries"
    order = 40

    def configure(self, parser):
        parser.add_argument("-n", "--lines", type=int, default=40)
        parser.add_argument("--level", choices=("error", "warn", "info", "debug"),
                            help="show this level and everything above it")

    def run(self, args, ctx):
        order = ["debug", "info", "warn", "error"]
        entries = read(ctx, lines=args.lines)
        if args.level:
            floor = order.index(args.level)
            entries = [e for e in entries if order.index(e["level"]) >= floor]
        if args.json:
            print(json.dumps(entries, indent=2))
            return 0
        for entry in entries:
            tone = {"error": "error", "warn": "warn"}.get(entry["level"], "dim")
            print("%s %s %s" % (paint(entry["time"], "dim", args.color),
                                paint("%-5s" % entry["level"], tone, args.color),
                                entry["message"]))
        return 0
