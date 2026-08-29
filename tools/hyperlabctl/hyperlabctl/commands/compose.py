import json

from ..composer import (
    RESOURCE_PROFILES,
    build_spec,
    find_spec,
    image_entry,
    remove_spec,
    write_spec,
)
from ..config import load_yaml
from ..errors import ContractError
from ..inventory import domain_names
from ..registry import target_choices
from .base import Command


def _memory(value):
    if value == "auto":
        return value
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError("memory must be auto or an integer") from exc


class ComposeCommand(Command):
    name = "compose"
    help = "create and manage host-local VM specs"
    order = 19

    def configure(self, parser):
        sub = parser.add_subparsers(dest="compose_action", required=True)

        write = sub.add_parser("write")
        write.add_argument("--name", required=True)
        write.add_argument("--image", required=True)
        write.add_argument(
            "--lifecycle",
            choices=("permanent", "disposable"),
            required=True,
        )
        write.add_argument(
            "--device-profile",
            choices=("standard", "vfio"),
            required=True,
        )
        write.add_argument("--network-profile", required=True)
        write.add_argument("--owner", required=True)
        write.add_argument("--purpose")
        write.add_argument(
            "--resource-profile",
            choices=RESOURCE_PROFILES,
            default="balanced",
        )
        write.add_argument("--memory", default="auto")
        write.add_argument("--vcpus", type=int, default=4)
        write.add_argument("--disk-gib", type=int)
        write.add_argument("--clipboard", action="store_true")
        write.add_argument("--dry-run", action="store_true")
        write.add_argument("--replace", action="store_true")
        write.add_argument("--confirm-replace")

        sub.add_parser("list")
        show = sub.add_parser("show")
        show.add_argument("name")
        delete = sub.add_parser("delete")
        delete.add_argument("name")
        delete.add_argument("--confirm", required=True)

    def run(self, args, ctx):
        if args.compose_action == "write":
            return self._write(args, ctx)
        if args.compose_action == "list":
            return self._list(args, ctx)
        if args.compose_action == "show":
            return self._show(args, ctx)
        return self._delete(args, ctx)

    def _write(self, args, ctx):
        if args.replace and args.confirm_replace != args.name:
            raise ContractError(
                "--replace requires --confirm-replace %s" % args.name
            )
        spec = build_spec(
            ctx.config.repo_root,
            name=args.name,
            image_id=args.image,
            lifecycle=args.lifecycle,
            device_profile=args.device_profile,
            network_profile=args.network_profile,
            owner=args.owner,
            purpose=args.purpose,
            resource_profile=args.resource_profile,
            memory_mb=_memory(args.memory),
            vcpus=args.vcpus,
            disk_gib=args.disk_gib,
            clipboard=args.clipboard,
        )
        entry = image_entry(ctx.config.repo_root, args.image)
        path = "vm-specs/.generated/%s.yml" % args.name
        if not args.dry_run:
            path = write_spec(ctx.config.repo_root, spec, replace=args.replace)
        result = {
            "path": path,
            "written": not args.dry_run,
            "image": entry,
            "spec": spec,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(("%s " % ("would write" if args.dry_run else "wrote")) + path)
        return 0

    def _list(self, args, ctx):
        rows = []
        for path in target_choices("spec", ctx.config.repo_root):
            spec = load_yaml(ctx.config.repo_root / path)
            rows.append({
                "path": path,
                "spec": spec,
                "image": image_entry(
                    ctx.config.repo_root,
                    spec.get("image"),
                ),
            })
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0
        for row in rows:
            spec = row["spec"]
            print("%-24s %-12s %-10s %-8s %s" % (
                spec.get("name"),
                spec.get("image"),
                spec.get("lifecycle"),
                spec.get("device_profile"),
                row["path"],
            ))
        return 0

    def _show(self, args, ctx):
        path = find_spec(ctx.config.repo_root, args.name)
        spec = load_yaml(ctx.config.repo_root / path)
        result = {
            "path": path,
            "spec": spec,
            "image": image_entry(ctx.config.repo_root, spec.get("image")),
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(path)
        return 0

    def _delete(self, args, ctx):
        if args.name in domain_names(ctx):
            raise ContractError(
                "destroy domain %s before removing its generated spec" % args.name
            )
        path = remove_spec(ctx.config.repo_root, args.name, args.confirm)
        if args.json:
            print(json.dumps({"removed": path}))
        else:
            print("removed %s" % path)
        return 0
