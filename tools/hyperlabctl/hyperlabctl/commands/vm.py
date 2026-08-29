import json
import shutil
import subprocess
from pathlib import Path

from .. import document as doc
from ..errors import ContractError, Unavailable
from ..inventory import domain_detail
from ..registry import target_choices
from .base import Command


class VmCommand(Command):
    name = "vm"
    help = "list, inspect and move domains"
    order = 15

    def configure(self, parser):
        sub = parser.add_subparsers(dest="vm_action", required=True)
        sub.add_parser("list", help="every domain with state and allocation")
        for action in ("start", "stop", "inspect"):
            child = sub.add_parser(action)
            child.add_argument("domain")
        inventory = sub.add_parser(
            "inventory",
            help="publish strict runtime inventory for one managed guest",
        )
        inventory.add_argument("spec")

    def run(self, args, ctx):
        if args.vm_action == "list":
            return self._list(args, ctx)
        if args.vm_action == "inspect":
            return self._inspect(args, ctx)
        if args.vm_action == "inventory":
            return self._inventory(args, ctx)
        return self._move(args, ctx)

    def _list(self, args, ctx):
        document = doc.build(ctx, only={"domains", "memory", "host"})
        domains = document.get("domains") or []
        if args.json:
            print(json.dumps(domains, indent=2))
            return 0
        for domain in domains:
            note = ""
            if domain["blocked"]:
                note = "  blocked: short %d MB" % domain["blocked"]["short_mb"]
            print("%-26s %-10s %8s %s%s" % (
                domain["name"], domain["state"],
                "%s MB" % domain["memory_mb"] if domain["memory_mb"] else "-",
                domain["network"] or "-", note))
        return 0

    def _inspect(self, args, ctx):
        detail = domain_detail(ctx, args.domain)
        if args.json:
            print(json.dumps(detail, indent=2))
        else:
            for key in ("name", "state", "memory_mb", "networks", "hostdevs", "vfio"):
                print("%-12s %s" % (key, detail[key]))
        return 0

    def _inventory_paths(self, ctx, spec):
        repo_value = ctx.config.repo_root
        if repo_value is None:
            raise Unavailable(
                "no HyperLab checkout is available for inventory publication"
            )

        repo_root = Path(repo_value).resolve()
        if spec not in target_choices("spec", repo_root):
            raise ContractError(
                "%s is not a checked-in or generated spec target" % spec
            )

        base_inventory = repo_root / "inventory.ini"
        playbook = repo_root / "playbooks/vm-guest-inventory.yml"

        for candidate, label in (
            (base_inventory, "base inventory"),
            (playbook, "runtime inventory playbook"),
        ):
            if candidate.is_symlink() or not candidate.is_file():
                raise Unavailable(
                    "%s is unavailable: %s" % (label, candidate)
                )

        return repo_root, base_inventory, playbook

    def _inventory(self, args, ctx):
        repo_root, base_inventory, playbook = self._inventory_paths(
            ctx,
            args.spec,
        )

        executable = shutil.which("ansible-playbook")
        if executable is None:
            raise Unavailable(
                "ansible-playbook is unavailable for inventory publication"
            )

        try:
            result = subprocess.run(
                [
                    executable,
                    "-i",
                    str(base_inventory),
                    str(playbook),
                    "-e",
                    "guest_spec=%s" % args.spec,
                ],
                cwd=repo_root,
                check=False,
                timeout=30.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise Unavailable(
                "runtime inventory publication timed out"
            ) from exc

        return result.returncode

    def _move(self, args, ctx):
        """start and stop stay unprivileged: the libvirt group already allows
        them. The refusal lives in operations.py so the panel refuses the same
        way, with the same numbers."""
        from ..operations import start, stop
        outcome = start(ctx, args.domain) if args.vm_action == "start" else stop(ctx, args.domain)
        print(outcome.message)
        return 0 if outcome.ok else 2
