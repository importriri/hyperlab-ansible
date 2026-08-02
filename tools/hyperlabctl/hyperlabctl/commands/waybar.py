import json

from .. import document as doc
from ..render import as_waybar, waybar_field
from .base import Command

FIELDS = ("summary", "trust", "ram", "gpu", "vms")


class WaybarCommand(Command):
    name = "waybar"
    help = "one JSON line in the shape waybar's custom module reads"
    order = 30

    def configure(self, parser):
        parser.add_argument("--field", choices=FIELDS, default="summary",
                            help="which pill of the drawer to render")

    def run(self, args, ctx):
        document = doc.build(ctx)
        if args.field == "summary":
            payload = as_waybar(document)
        else:
            payload = waybar_field(document, args.field)
        print(json.dumps(payload), flush=True)
        return 0
