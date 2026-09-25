import json

from .. import document as doc
from ..render import paint
from .base import Command


class TrustCommand(Command):
    name = "trust"
    help = "the ladder, where the GPU is on it, and what is still reachable"
    order = 22

    def run(self, args, ctx):
        built = doc.build(ctx, only={"trust", "gpu"})
        if built.get("trust") is None:
            # The trust state could not be read. That is unknown, never
            # "unclaimed": no level is reported as reachable.
            reason = next((problem["message"] for problem in built.get("problems") or []
                           if problem.get("provider") == "trust"),
                          "trust state could not be read")
            if args.json:
                print(json.dumps({"claimed": None, "level": None, "known": False,
                                  "ladder": [], "problem": reason}, indent=2))
            else:
                print("GPU trust state is unknown: %s" % reason)
            return 1
        trust = built["trust"]
        ladder = sorted((trust.get("ladder") or {}).items(),
                        key=lambda pair: pair[1], reverse=True)
        current = trust.get("level")
        rows = [{"name": name, "level": level,
                 "reachable": current is None or level <= current,
                 "current": level == current}
                for name, level in ladder]
        if args.json:
            print(json.dumps({"claimed": trust.get("claimed"), "level": current,
                              "ladder": rows}, indent=2))
            return 0
        if current is None:
            print("GPU unclaimed this boot: every level is still reachable")
        else:
            print("GPU held at %s (%s). Trust only rises through a reboot."
                  % (trust.get("name"), current))
        for row in rows:
            mark = "->" if row["current"] else "  "
            label = "reachable" if row["reachable"] else "needs a reboot"
            print("  %s %-8s %d  %s" % (mark, row["name"], row["level"],
                                        paint(label, "ok" if row["reachable"] else "warn",
                                              args.color)))
        return 0
