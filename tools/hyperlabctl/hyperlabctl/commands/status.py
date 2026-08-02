from .. import document as doc
from ..render import as_json, as_text
from .base import Command


class StatusCommand(Command):
    name = "status"
    help = "the whole lab in one document"
    order = 10

    def configure(self, parser):
        parser.add_argument("--only", action="append", metavar="SECTION",
                            help="limit to one section; repeatable")

    def run(self, args, ctx):
        document = doc.build(ctx, only=set(args.only) if args.only else None)
        if args.json:
            print(as_json(document))
        else:
            print(as_text(document, color=args.color))
        return 2 if doc.worst_severity(document) == "error" else 0
