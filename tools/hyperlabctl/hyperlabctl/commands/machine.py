"""C10 product Machine catalogue, registry and derived adapter surface."""

from __future__ import annotations

import datetime
import getpass
import json
from pathlib import Path
from typing import Any

from .. import document as doc
from ..errors import Unavailable
from ..machine_factory import (
    create_from_template,
    image_os_label,
    template_catalog,
    write_projected_vm_spec,
)
from ..machine_registry import (
    list_machines,
    read_machine,
)
from ..render import machine_cards
from .base import Command


def _repo_root(ctx) -> Path:
    value = ctx.config.repo_root

    if value is None:
        raise Unavailable(
            "no HyperLab checkout is available"
        )

    return Path(value).resolve()


def _created_at() -> str:
    return (
        datetime.datetime.now(
            datetime.timezone.utc
        )
        .isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )


def _intent_row(
    record: dict[str, Any],
    state: str,
) -> dict[str, Any]:
    resources = record["resources"]

    if state == "runtime-unavailable":
        gpu_text = "Runtime unavailable"
    elif state == "configuration-drift":
        gpu_text = "Runtime configuration drift"
    else:
        gpu_text = "Runtime not created"

    return {
        "name": record["id"],
        "display_name": record["display_name"],
        "state": state,
        # A persistent Machine request is not observed provenance.
        "provenance": "unclassified",
        "gpu": gpu_text,
        "gpu_relation": "unknown",
        "memory_mb": resources["memory_mb"],
        "vcpus": resources["vcpus"],
        # Runtime network attachment is unknown until libvirt says otherwise.
        "network": None,
        "networks": None,
        "managed": None,
        "product_managed": True,
        "vfio": None,
        "lifecycle": record["lifecycle"],
        "device_capability": record["device_capability"],
        "network_profile": record["network_profile"],
        "gpu_handoff_profile": record["gpu_handoff_profile"],
        "template": dict(record["template"]),
        "image": dict(record["image"]),
        "blocked": None,
        "runtime_present": False,
        "runtime_drift": False,
    }


def _runtime_matches_machine(
    runtime: dict[str, Any],
    record: dict[str, Any],
) -> bool:
    return (
        runtime.get("managed") is True
        and runtime.get("product_managed") is True
        and runtime.get("image")
        == record["image"]["id"]
        and runtime.get("image_sha256")
        == record["image"]["sha256"]
        and runtime.get("lifecycle")
        == record["lifecycle"]
        and runtime.get("device_profile")
        == record["device_capability"]
        and runtime.get("trust_profile")
        == record["network_profile"]
        and runtime.get("gpu_handoff_profile")
        == record["gpu_handoff_profile"]
        and (
            (
                runtime.get("gpu_policy_state")
                == "verified"
                and runtime.get("gpu_trust_profile")
                == record["gpu_handoff_profile"]
            )
            if record["device_capability"] == "vfio"
            else runtime.get("gpu_policy_state")
            == "not-required"
        )
    )


def build_product_inventory(
    ctx,
    *,
    state_home: Path | None = None,
) -> dict[str, Any]:
    """Merge persistent product intent with matching observed runtime only.

    Product membership comes exclusively from the C10 Machine registry.
    Libvirt domains that have no Machine record are deliberately invisible
    here and remain available through Diagnostics/raw inventory.
    """

    records = list_machines(
        state_home=state_home,
    )

    # First install is a valid, available and empty product inventory.
    # Do not touch libvirt just to discover that there are no product Machines.
    if not records:
        return {
            "text": "0/0",
            "class": "ok",
            "tooltip": "No product Machines created",
            "machines_available": True,
            "runtime_available": None,
            "machines": [],
        }

    document = doc.build(
        ctx,
        only={
            "domains",
            "gpu",
        },
    )

    runtime_available = isinstance(
        document.get("domains"),
        list,
    )

    runtime_by_name: dict[str, dict[str, Any]] = {}

    if runtime_available:
        runtime_by_name = {
            row["name"]: row
            for row in document["domains"]
        }

    repo_root = getattr(
        getattr(ctx, "config", None),
        "repo_root",
        None,
    )

    rows = []

    for record in records:
        machine_id = record["id"]

        if not runtime_available:
            row = _intent_row(
                record,
                "runtime-unavailable",
            )

        else:
            runtime = runtime_by_name.get(
                machine_id
            )

            if runtime is None:
                row = _intent_row(
                    record,
                    "not-created",
                )

            elif not _runtime_matches_machine(
                runtime,
                record,
            ):
                row = _intent_row(
                    record,
                    "configuration-drift",
                )

                row.update(
                    {
                        "runtime_present": True,
                        "runtime_drift": True,
                        "observed_state": runtime.get(
                            "state"
                        ),
                        "observed_managed": runtime.get(
                            "managed"
                        ),
                    }
                )

            else:
                row = machine_cards(
                    {
                        "domains": [runtime],
                        "gpu": document.get("gpu") or {},
                    }
                )[0]

                row.update(
                    {
                        "display_name": record[
                            "display_name"
                        ],
                        "product_managed": True,
                        "device_capability": record[
                            "device_capability"
                        ],
                        "network_profile": record[
                            "network_profile"
                        ],
                        "gpu_handoff_profile": record[
                            "gpu_handoff_profile"
                        ],
                        "template": dict(
                            record["template"]
                        ),
                        "image": dict(
                            record["image"]
                        ),
                        "runtime_present": True,
                        "runtime_drift": False,
                    }
                )

        # The operating system comes from the Machine's checked-in image,
        # not from anything the guest reports.
        row["os"] = (
            image_os_label(
                repo_root,
                record["image"]["id"],
            )
            if repo_root is not None
            else None
        )

        rows.append(
            row
        )

    running = sum(
        row["state"] == "running"
        for row in rows
    )

    drift = any(
        row["runtime_drift"]
        for row in rows
    )

    degraded = (
        runtime_available is False
        or drift
    )

    tooltip = (
        f"{len(rows)} product Machine"
        + (
            ""
            if len(rows) == 1
            else "s"
        )
    )

    if runtime_available is False:
        tooltip += "; libvirt runtime unavailable"
    elif drift:
        tooltip += "; runtime configuration drift detected"

    return {
        "text": f"{running}/{len(rows)}",
        "class": "warn" if degraded else "ok",
        "tooltip": tooltip,
        "machines_available": True,
        "runtime_available": runtime_available,
        "machines": rows,
    }


class MachineCommand(Command):
    name = "machine"
    help = "manage C10 product Machines"
    order = 14

    def configure(self, parser):
        sub = parser.add_subparsers(
            dest="machine_action",
            required=True,
        )

        sub.add_parser(
            "templates",
            help="list reviewed product Templates",
        )

        sub.add_parser(
            "list",
            help="list persistent product Machines",
        )

        show = sub.add_parser(
            "show",
            help="show one persistent product Machine",
        )
        show.add_argument(
            "machine_id",
        )

        sub.add_parser(
            "inventory",
            help="product Machines merged with matching runtime observations",
        )

        create = sub.add_parser(
            "create",
            help="create persistent Machine intent from a reviewed Template",
        )

        create.add_argument(
            "template_id",
        )
        create.add_argument(
            "machine_id",
        )
        create.add_argument(
            "--display-name",
        )
        create.add_argument(
            "--purpose",
        )
        create.add_argument(
            "--owner",
        )
        create.add_argument(
            "--lifecycle",
            choices=(
                "permanent",
                "disposable",
            ),
        )
        create.add_argument(
            "--device-capability",
            choices=(
                "standard",
                "vfio",
            ),
        )
        create.add_argument(
            "--gpu-handoff-profile",
            choices=(
                "clean",
                "dev",
                "dirty",
                "lab",
            ),
        )
        create.add_argument(
            "--network-profile",
            choices=(
                "clean",
                "dev",
                "services",
                "dirty",
                "lab",
            ),
        )
        create.add_argument(
            "--resource-profile",
            choices=(
                "minimum",
                "balanced",
                "performance",
                "custom",
            ),
        )
        create.add_argument(
            "--memory-mb",
            type=int,
        )
        create.add_argument(
            "--vcpus",
            type=int,
        )
        create.add_argument(
            "--disk-gib",
            type=int,
        )
        create.add_argument(
            "--looking-glass-mode",
            choices=(
                "disabled",
                "windows",
                "linux-experimental",
            ),
        )

        project = sub.add_parser(
            "project",
            help="write the derived legacy VM-spec adapter for one Machine",
        )
        project.add_argument(
            "machine_id",
        )

    def run(self, args, ctx):
        action = args.machine_action

        if action == "templates":
            return self._templates(
                args,
                ctx,
            )

        if action == "list":
            return self._list(
                args,
            )

        if action == "show":
            return self._show(
                args,
            )

        if action == "inventory":
            return self._inventory(
                args,
                ctx,
            )

        if action == "create":
            return self._create(
                args,
                ctx,
            )

        if action == "project":
            return self._project(
                args,
                ctx,
            )

        raise Unavailable(
            f"unsupported Machine action {action}"
        )

    def _templates(self, args, ctx):
        entries = template_catalog(
            _repo_root(
                ctx
            )
        )

        if args.json:
            print(
                json.dumps(
                    {
                        "templates": entries,
                    },
                    indent=2,
                )
            )
            return 0

        for entry in entries:
            state = (
                "ready"
                if entry["ready"]
                else "blocked"
            )

            print(
                "%-28s %-10s %s"
                % (
                    entry["id"],
                    entry["version"],
                    state,
                )
            )

        return 0

    def _list(self, args):
        records = list_machines()

        if args.json:
            print(
                json.dumps(
                    {
                        "machines": records,
                    },
                    indent=2,
                )
            )
            return 0

        for record in records:
            print(
                "%-28s %-11s %-8s %s"
                % (
                    record["id"],
                    record["lifecycle"],
                    record["device_capability"],
                    record["network_profile"],
                )
            )

        return 0

    def _show(self, args):
        record = read_machine(
            args.machine_id
        )

        print(
            json.dumps(
                record,
                indent=2,
            )
        )

        return 0

    def _inventory(self, args, ctx):
        payload = build_product_inventory(
            ctx
        )

        if args.json:
            print(
                json.dumps(
                    payload,
                    indent=2,
                )
            )
            return 0

        for row in payload["machines"]:
            print(
                "%-28s %-22s %-12s %s"
                % (
                    row["name"],
                    row["state"],
                    row["device_capability"],
                    row["network_profile"],
                )
            )

        return 0

    def _create(self, args, ctx):
        kwargs: dict[str, Any] = {
            "template_id": args.template_id,
            "machine_id": args.machine_id,
            "owner": (
                args.owner
                if args.owner is not None
                else getpass.getuser()
            ),
            "created_at": _created_at(),
        }

        optional = {
            "display_name": args.display_name,
            "purpose": args.purpose,
            "lifecycle": args.lifecycle,
            "device_capability": args.device_capability,
            "gpu_handoff_profile": args.gpu_handoff_profile,
            "network_profile": args.network_profile,
            "resource_profile": args.resource_profile,
            "memory_mb": args.memory_mb,
            "vcpus": args.vcpus,
            "disk_gib": args.disk_gib,
            "looking_glass_mode": args.looking_glass_mode,
        }

        for key, value in optional.items():
            if value is not None:
                kwargs[key] = value

        path = create_from_template(
            _repo_root(
                ctx
            ),
            **kwargs,
        )

        record = read_machine(
            args.machine_id
        )

        payload = {
            "record_path": str(
                path
            ),
            "machine": record,
        }

        if args.json:
            print(
                json.dumps(
                    payload,
                    indent=2,
                )
            )
        else:
            print(
                "created %s"
                % record["id"]
            )

        return 0

    def _project(self, args, ctx):
        record = read_machine(
            args.machine_id
        )

        spec = write_projected_vm_spec(
            _repo_root(
                ctx
            ),
            record,
        )

        payload = {
            "machine": record["id"],
            "spec": spec,
        }

        if args.json:
            print(
                json.dumps(
                    payload,
                    indent=2,
                )
            )
        else:
            print(
                spec
            )

        return 0
