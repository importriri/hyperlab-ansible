import json

from .. import document as doc
from ..remedies import remedy
from ..render import paint
from .base import Command


class DoctorCommand(Command):
    name = "doctor"
    help = "every problem, with the command that clears it"
    order = 45

    def run(self, args, ctx):
        built = doc.build(ctx)
        problems = built.get("problems") or []
        listed = []
        for problem in problems:
            entry = dict(problem)
            entry["remedy"] = remedy(problem, built)
            listed.append(entry)

        if args.json:
            print(json.dumps(listed, indent=2))
        elif not listed:
            print(paint("nothing to report", "ok", args.color))
        else:
            for entry in listed:
                print("%s  %s" % (paint(entry["severity"].upper(), entry["severity"], args.color),
                                  entry["message"]))
                print("      %s: %s" % (entry["provider"], entry["id"]))
                if entry["remedy"]:
                    print("      fix: %s" % paint(entry["remedy"], "ok", args.color))
                print("")
        return 2 if any(entry["severity"] == "error" for entry in listed) else 0
