import json

from .. import document as doc
from ..render import as_waybar, waybar_field
from .base import Command


class WatchCommand(Command):
    name = "watch"
    help = "stream one JSON line per libvirt event, for a continuous bar module"
    order = 35

    def configure(self, parser):
        from .waybar import FIELDS
        parser.add_argument("--field", choices=FIELDS, default="summary")
        parser.add_argument("--heartbeat", type=positive_seconds, default=60, metavar="SECONDS",
                            help="emit anyway after this long with no event")
        parser.add_argument("--max-cycles", type=int, default=0,
                            help=argparse_suppress())

    def run(self, args, ctx):
        """Blocks on libvirt instead of polling it.

        ``virsh event --timeout N`` returns on an event or after N seconds. The
        Python timeout is deliberately slightly longer: it protects a wedged
        virsh without cutting a 60-second heartbeat down to Runner's ordinary
        15-second command timeout.
        """
        cycles = 0
        while True:
            self._emit(ctx, args.field)
            cycles += 1
            if args.max_cycles and cycles >= args.max_cycles:
                return 0
            result = ctx.virsh_uncached(
                "event", "--all", "--timeout", str(args.heartbeat),
                timeout=args.heartbeat + 5,
            )
            if result.rc == 0:
                continue
            timed_out = (result.rc == 1 and
                         ("event loop timed out" in result.stdout.lower() or
                          "events received: 0" in result.stdout.lower()))
            if timed_out:
                continue
            return 2

    def _emit(self, ctx, field):
        ctx.cache.clear()
        document = doc.build(ctx)
        payload = as_waybar(document) if field == "summary" else waybar_field(document, field)
        print(json.dumps(payload), flush=True)


def positive_seconds(value):
    parsed = int(value)
    if parsed < 1:
        import argparse
        raise argparse.ArgumentTypeError("heartbeat must be at least one second")
    return parsed


def argparse_suppress():
    import argparse
    return argparse.SUPPRESS
