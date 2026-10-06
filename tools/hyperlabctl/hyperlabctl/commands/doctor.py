import json
from pathlib import Path

import yaml

from .. import document as doc
from .. import hardware
from ..remedies import remedy
from ..render import paint
from .base import Command


class DoctorCommand(Command):
    name = "doctor"
    help = "every problem, with the command that clears it"
    order = 45

    def configure(self, parser):
        parser.add_argument("--hardware", action="store_true",
                            help="whether this computer can run HyperLab, read without privilege")
        parser.add_argument("--profile", metavar="NAME",
                            help="with --hardware: print a host profile proposal named NAME to review")

    def run(self, args, ctx):
        if args.profile and not args.hardware:
            print("hyperlabctl: --profile goes with --hardware")
            return 2
        if args.hardware:
            return self.hardware(args, ctx)
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

    def hardware(self, args, ctx):
        """Readiness before install (ADR 0050). Exit 2 on a failed check."""
        facts = hardware.read_host(Path(ctx.environ.get("HYPERLAB_HARDWARE_ROOT") or "/"))
        checks = hardware.assess(facts)
        failed = any(item["status"] == "fail" for item in checks)
        if args.profile:
            if not hardware.PROFILE_NAME_RE.fullmatch(args.profile):
                print("hyperlabctl: a profile name is lowercase letters, digits and dashes")
                return 2
            proposal = hardware.profile(facts, args.profile)
            if args.json:
                print(json.dumps({"checks": checks, "profile": proposal}, indent=2))
            else:
                print("# A host profile proposal from hyperlabctl doctor --hardware.")
                print("# Review every value before adding it under host_profiles in")
                print("# group_vars/all/hardware.yml: HyperLab never trusts it on its own.")
                print("# keyboard_layout comes from /etc/vconsole.conf; the evidence fields")
                print("# stay null until a preflight report is reviewed.")
                print(yaml.safe_dump(proposal, sort_keys=False, default_flow_style=None), end="")
            return 2 if failed else 0
        if args.json:
            print(json.dumps({"checks": checks}, indent=2))
        else:
            for item in checks:
                severity = {"ok": "ok", "warn": "warn", "fail": "error"}[item["status"]]
                print("%s  %s" % (paint(item["status"].upper().ljust(4), severity, args.color), item["message"]))
                if item["fix"] and item["status"] != "ok":
                    print("      fix: %s" % item["fix"])
        return 2 if failed else 0
