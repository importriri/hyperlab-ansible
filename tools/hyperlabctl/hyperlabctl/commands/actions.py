import json
import shlex

from ..registry import actions, resolve, target_choices
from .base import Command


class ActionsCommand(Command):
    name = "actions"
    help = "list or safely resolve actions used by the palette"
    order = 20

    def configure(self, parser):
        parser.add_argument("--unprivileged", action="store_true",
                            help="only what a session may run without a password")
        parser.add_argument("--all", dest="show_all", action="store_true",
                            help="include actions whose playbook is not in this checkout yet")
        parser.add_argument("--resolve", metavar="ACTION_ID",
                            help="resolve one action to a safely quoted command")
        parser.add_argument("--choices", choices=("spec", "manifest"),
                            help="list checked-in targets for the palette")
        parser.add_argument("--domain")
        parser.add_argument("--spec")
        parser.add_argument("--manifest")

    def run(self, args, ctx):
        if args.resolve:
            argv = resolve(args.resolve, repo_root=ctx.config.repo_root,
                           domain=args.domain, spec=args.spec, manifest=args.manifest)
            print(json.dumps(argv) if args.json else shlex.join(argv))
            return 0
        if args.choices:
            listed = target_choices(args.choices, ctx.config.repo_root)
            print(json.dumps(listed, indent=2) if args.json else "\n".join(listed))
            return 0

        listed = actions(include_privileged=not args.unprivileged,
                         repo_root=ctx.config.repo_root,
                         include_unavailable=args.show_all)
        if args.json:
            print(json.dumps(listed, indent=2))
            return 0
        for action in listed:
            flags = []
            if action["privileged"]:
                flags.append("privileged")
            if action["destructive"]:
                flags.append("destructive")
            if not action["available"]:
                flags.append("needs %s" % action["requires"])
            print("%-16s %-38s %s" % (action["id"], action["label"],
                                      ", ".join(flags) or "-"))
        return 0
