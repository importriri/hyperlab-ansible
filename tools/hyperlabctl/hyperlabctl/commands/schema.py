import json

from .. import SCHEMA_VERSION
from ..providers import providers
from .base import Command


class SchemaCommand(Command):
    name = "schema"
    help = "the shape of the status document, and who fills each section"
    order = 50

    def run(self, args, ctx):
        sections = [{"key": provider.key, "order": provider.order,
                     "summary": provider.summary,
                     "module": type(provider).__module__}
                    for provider in providers()]
        payload = {"schema_version": SCHEMA_VERSION, "sections": sections}
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        print("schema version %d" % SCHEMA_VERSION)
        for section in sections:
            external = "  (external)" if not section["module"].startswith("hyperlabctl.") else ""
            print("  %-10s %s%s" % (section["key"], section["summary"], external))
        return 0
