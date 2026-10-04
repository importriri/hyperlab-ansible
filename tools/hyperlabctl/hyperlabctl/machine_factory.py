"""C10 Template catalogue and Machine intent materialization.

This module converts reviewed checked-in Template policy into persistent
Machine intent. It does not define, start, stop or inspect libvirt domains.

Observed runtime state remains owned by the existing runtime providers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .composer import write_spec
from .config import load_yaml
from .errors import ContractError, Unavailable
from .machine_registry import (
    create_machine,
    validate_machine_record,
)

# The reviewed contamination ladder. A handoff profile may lower, never raise,
# the class a ranked network identity implies; services is not ranked.
GPU_HANDOFF_LADDER = {"clean": 3, "dev": 2, "dirty": 1, "lab": 0}


ID_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]*$"
)

MACHINE_ID_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]{1,30}$"
)

SHA256_RE = re.compile(
    r"^[a-f0-9]{64}$"
)

LOOKING_GLASS_MODES = {
    "disabled",
    "windows",
    "linux-experimental",
}

RESOURCE_PROFILES = {
    "minimum",
    "balanced",
    "performance",
    "custom",
}


def _repo_root(
    repo_root: Path | str | None,
) -> Path:
    if repo_root is None:
        raise Unavailable(
            "no repository checkout found"
        )

    root = Path(
        repo_root
    ).resolve()

    for name in (
        "images",
        "templates",
    ):
        path = root / name

        if path.is_symlink():
            raise ContractError(
                f"{name}/ must not be a symlink"
            )

        if not path.is_dir():
            raise Unavailable(
                f"repository is missing {name}/ "
                f"under {root}"
            )

    return root


def _identifier(
    value: Any,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or ID_RE.fullmatch(value) is None
    ):
        raise ContractError(
            f"{label} has an invalid identifier"
        )

    return value


def _mapping(
    value: Any,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(
            f"{label} must be a mapping"
        )

    return value


def _named_document(
    root: Path,
    directory: str,
    identifier: str,
) -> tuple[Path, dict[str, Any]]:
    identifier = _identifier(
        identifier,
        directory.rstrip("/"),
    )

    path = (
        root
        / directory
        / f"{identifier}.yml"
    )

    try:
        path.lstat()
    except FileNotFoundError as exc:
        raise ContractError(
            f"unknown {directory.rstrip('/')} "
            f"{identifier}"
        ) from exc
    except OSError as exc:
        raise Unavailable(
            f"cannot inspect {path}"
        ) from exc

    if path.is_symlink() or not path.is_file():
        raise ContractError(
            f"{path} must be a real file"
        )

    document = load_yaml(
        path
    )

    if not isinstance(document, dict):
        raise ContractError(
            f"{path} must contain a mapping"
        )

    if document.get("id") != identifier:
        raise ContractError(
            f"{path} id must equal its file name"
        )

    return path, document


def _image(
    root: Path,
    image_id: str,
) -> dict[str, Any]:
    _, image = _named_document(
        root,
        "images",
        image_id,
    )

    return image


OS_NAMES = {
    "archlinux": "Arch Linux",
    "debian": "Debian",
    "fedora": "Fedora",
    "parrot": "Parrot OS",
    "ubuntu": "Ubuntu",
    "win": "Windows",
}

OS_VARIANT_RE = re.compile(
    r"^(archlinux|debian|fedora|parrot|ubuntu|win)([0-9]+(?:\.[0-9]+)?)?$"
)


def os_label(
    image: dict[str, Any],
) -> str | None:
    """The operating system a Machine runs, from its checked-in image.

    Read from the host's reviewed image manifest, never from the guest, so
    a guest cannot rename itself. An unknown variant is reported as unknown
    rather than guessed.
    """
    variant = image.get("os_variant")
    if not isinstance(variant, str):
        return None
    match = OS_VARIANT_RE.fullmatch(variant)
    if match is None:
        return None
    name = OS_NAMES[match.group(1)]
    return f"{name} {match.group(2)}" if match.group(2) else name


def image_os_label(
    repo_root: Path | str,
    image_id: str,
) -> str | None:
    try:
        return os_label(_image(_repo_root(repo_root), image_id))
    except (ContractError, Unavailable):
        return None


def _sealed_image(
    image: dict[str, Any],
) -> bool:
    digest = image.get(
        "sha256"
    )

    return (
        image.get("status") == "sealed"
        and isinstance(digest, str)
        and SHA256_RE.fullmatch(digest)
        is not None
    )


def _enabled(
    mapping: Any,
    names: tuple[str, ...],
    label: str,
) -> list[str]:
    mapping = _mapping(
        mapping,
        label,
    )

    result = [
        name
        for name in names
        if mapping.get(name) is True
    ]

    if not result:
        raise ContractError(
            f"{label} enables no choices"
        )

    return result


def _gpu_handoff_profiles(
    template: dict[str, Any],
    devices: list[str],
) -> list[str]:
    mapping = _mapping(
        template.get("gpu_handoff_profiles"),
        "Template gpu_handoff_profiles",
    )

    result = [
        name
        for name in (
            "clean",
            "dev",
            "dirty",
            "lab",
        )
        if mapping.get(name) is True
    ]

    if "vfio" in devices and not result:
        raise ContractError(
            "VFIO Template enables no "
            "GPU handoff profile"
        )

    return result


def _networks(
    template: dict[str, Any],
    image: dict[str, Any],
) -> list[str]:
    values = template.get(
        "network_allowlist"
    )

    if not isinstance(values, list) or not values:
        raise ContractError(
            "Template needs a non-empty network_allowlist"
        )

    image_values = image.get(
        "network_allowlist"
    )

    if not isinstance(image_values, list):
        raise ContractError(
            "image network_allowlist is invalid"
        )

    result: list[str] = []

    for value in values:
        if (
            not isinstance(value, str)
            or not value
        ):
            raise ContractError(
                "Template contains an invalid network"
            )

        if value not in image_values:
            raise ContractError(
                f"Template network {value} "
                "is not permitted by its image"
            )

        if value not in result:
            result.append(
                value
            )

    return result


def _validate_template(
    template: dict[str, Any],
    image: dict[str, Any],
) -> None:
    if template.get(
        "schema_version"
    ) != 1:
        raise ContractError(
            "unsupported Template schema_version"
        )

    _identifier(
        template.get("id"),
        "Template id",
    )

    version = template.get(
        "version"
    )

    if not isinstance(version, str) or not version:
        raise ContractError(
            "Template version is required"
        )

    if template.get("status") not in {
        "draft",
        "ready",
    }:
        raise ContractError(
            "Template status is unsupported"
        )

    if not image.get(
        "generalized"
    ):
        raise ContractError(
            "Template image is not generalized"
        )

    if image.get(
        "contains_personal_data"
    ):
        raise ContractError(
            "Template image contains personal data"
        )

    devices = _enabled(
        template.get(
            "device_capabilities"
        ),
        (
            "standard",
            "vfio",
        ),
        "Template device_capabilities",
    )

    image_supports = _mapping(
        image.get("supports"),
        "image supports",
    )

    for device in devices:
        if image_supports.get(
            device
        ) is not True:
            raise ContractError(
                f"Template enables {device} "
                "but image does not support it"
            )

    gpu_handoff_profiles = (
        _gpu_handoff_profiles(
            template,
            devices,
        )
    )

    _enabled(
        template.get(
            "lifecycles"
        ),
        (
            "permanent",
            "disposable",
        ),
        "Template lifecycles",
    )

    _networks(
        template,
        image,
    )

    profiles = _enabled(
        template.get(
            "resource_profiles"
        ),
        (
            "minimum",
            "balanced",
            "performance",
            "custom",
        ),
        "Template resource_profiles",
    )

    defaults = _mapping(
        template.get("defaults"),
        "Template defaults",
    )

    lifecycles = _enabled(
        template.get(
            "lifecycles"
        ),
        (
            "permanent",
            "disposable",
        ),
        "Template lifecycles",
    )

    networks = _networks(
        template,
        image,
    )

    if defaults.get(
        "lifecycle"
    ) not in lifecycles:
        raise ContractError(
            "Template default lifecycle "
            "is not enabled"
        )

    default_device = defaults.get(
        "device_capability"
    )

    if default_device not in devices:
        raise ContractError(
            "Template default device capability "
            "is not enabled"
        )

    default_gpu_handoff = defaults.get(
        "gpu_handoff_profile"
    )

    if default_device == "vfio":
        if default_gpu_handoff not in gpu_handoff_profiles:
            raise ContractError(
                "Template default GPU handoff "
                "profile is not enabled"
            )
    elif default_gpu_handoff is not None:
        raise ContractError(
            "standard Template default cannot "
            "carry gpu_handoff_profile"
        )

    if defaults.get(
        "network_profile"
    ) not in networks:
        raise ContractError(
            "Template default network "
            "is not enabled"
        )

    if defaults.get(
        "resource_profile"
    ) not in profiles:
        raise ContractError(
            "Template default resource profile "
            "is not enabled"
        )

    presentation = _mapping(
        template.get("presentation"),
        "Template presentation",
    )

    mode = presentation.get(
        "looking_glass_mode"
    )

    if mode not in LOOKING_GLASS_MODES:
        raise ContractError(
            "Template Looking Glass mode "
            "is unsupported"
        )

    recovery_console = presentation.get(
        "recovery_console"
    )

    if not isinstance(
        recovery_console,
        bool,
    ):
        raise ContractError(
            "Template recovery_console "
            "must be boolean"
        )

    _identifier(
        presentation.get(
            "workspace_profile"
        ),
        "Template workspace_profile",
    )

    if (
        mode != "disabled"
        and "vfio" not in devices
    ):
        raise ContractError(
            "Looking Glass capability "
            "requires VFIO"
        )

    os_family = image.get(
        "os_family"
    )

    if (
        mode == "windows"
        and os_family != "windows"
    ):
        raise ContractError(
            "Windows Looking Glass mode "
            "requires a Windows image"
        )

    if (
        mode == "linux-experimental"
        and os_family != "linux"
    ):
        raise ContractError(
            "Linux Looking Glass mode "
            "requires a Linux image"
        )


def _template_document(
    repo_root: Path | str,
    template_id: str,
) -> tuple[
    Path,
    dict[str, Any],
    dict[str, Any],
]:
    root = _repo_root(
        repo_root
    )

    path, template = _named_document(
        root,
        "templates",
        template_id,
    )

    image_id = _identifier(
        template.get("image"),
        "Template image",
    )

    image = _image(
        root,
        image_id,
    )

    _validate_template(
        template,
        image,
    )

    return path, template, image


def template_catalog(
    repo_root: Path | str,
) -> list[dict[str, Any]]:
    root = _repo_root(
        repo_root
    )

    entries = []

    for path in sorted(
        (root / "templates").glob("*.yml")
    ):
        if path.is_symlink():
            raise ContractError(
                f"Template must not be a symlink: {path}"
            )

        template_id = path.stem

        _, template, image = _template_document(
            root,
            template_id,
        )

        ready = (
            template.get("status") == "ready"
            and _sealed_image(image)
        )

        blocked_reason = None

        if template.get("status") != "ready":
            blocked_reason = (
                "Template is not ready"
            )
        elif not _sealed_image(image):
            blocked_reason = (
                "Golden Image is not sealed "
                "with a valid digest"
            )

        entries.append(
            {
                "id": template["id"],
                "display_name": (
                    template.get("display_name")
                    or template["id"]
                ),
                "version": template["version"],
                "status": template["status"],
                "ready": ready,
                "blocked_reason": blocked_reason,
                "image": {
                    "id": image["id"],
                    "sha256": (
                        image.get("sha256")
                        if ready
                        else None
                    ),
                },
                "lifecycles": _enabled(
                    template["lifecycles"],
                    (
                        "permanent",
                        "disposable",
                    ),
                    "Template lifecycles",
                ),
                "device_capabilities": _enabled(
                    template[
                        "device_capabilities"
                    ],
                    (
                        "standard",
                        "vfio",
                    ),
                    "Template device_capabilities",
                ),
                "network_profiles": _networks(
                    template,
                    image,
                ),
                "resource_profiles": _enabled(
                    template[
                        "resource_profiles"
                    ],
                    (
                        "minimum",
                        "balanced",
                        "performance",
                        "custom",
                    ),
                    "Template resource_profiles",
                ),
                "presentation": dict(
                    template["presentation"]
                ),
                "defaults": dict(
                    template["defaults"]
                ),
                "source": path.relative_to(
                    root
                ).as_posix(),
            }
        )

    return entries


def template_entry(
    repo_root: Path | str,
    template_id: str,
) -> dict[str, Any]:
    for entry in template_catalog(
        repo_root
    ):
        if entry["id"] == template_id:
            return entry

    raise ContractError(
        f"unknown Template {template_id}"
    )


def _resource_values(
    image: dict[str, Any],
    profile: str,
    *,
    memory_mb: int | str | None,
    vcpus: int | None,
    disk_gib: int | None,
) -> dict[str, Any]:
    virtual = image.get(
        "virtual_size_gib"
    )
    minimum = image.get(
        "minimum_size_gib"
    )
    memory_floor = image.get(
        "min_memory_mb"
    )

    if (
        not isinstance(virtual, int)
        or isinstance(virtual, bool)
        or virtual < 1
    ):
        raise ContractError(
            "image virtual_size_gib "
            "must be a positive integer"
        )

    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or minimum < 1
    ):
        raise ContractError(
            "image minimum_size_gib "
            "must be a positive integer"
        )

    if (
        not isinstance(memory_floor, int)
        or isinstance(memory_floor, bool)
        or memory_floor < 512
    ):
        raise ContractError(
            "image min_memory_mb "
            "must be an integer >= 512"
        )

    if profile == "custom":
        resources = {
            "memory_mb": memory_mb,
            "vcpus": vcpus,
            "disk_gib": disk_gib,
        }
    elif profile == "minimum":
        resources = {
            "memory_mb": memory_floor,
            "vcpus": 2,
            "disk_gib": max(
                virtual,
                minimum,
            ),
        }
    elif profile == "performance":
        resources = {
            "memory_mb": "auto",
            "vcpus": 6,
            "disk_gib": max(
                virtual,
                96
                if image.get("os_family")
                == "windows"
                else 40,
            ),
        }
    elif profile == "balanced":
        resources = {
            "memory_mb": "auto",
            "vcpus": 4,
            "disk_gib": max(
                virtual,
                64
                if image.get("os_family")
                == "windows"
                else 20,
            ),
        }
    else:
        raise ContractError(
            f"unknown resource profile {profile}"
        )

    memory = resources[
        "memory_mb"
    ]

    if memory != "auto" and (
        not isinstance(memory, int)
        or isinstance(memory, bool)
        or memory < 512
    ):
        raise ContractError(
            "memory_mb must be auto "
            "or an integer >= 512"
        )

    cpu_count = resources[
        "vcpus"
    ]

    if (
        not isinstance(cpu_count, int)
        or isinstance(cpu_count, bool)
        or not 1 <= cpu_count <= 256
    ):
        raise ContractError(
            "vcpus must be an integer "
            "between 1 and 256"
        )

    disk = resources[
        "disk_gib"
    ]

    if (
        not isinstance(disk, int)
        or isinstance(disk, bool)
        or disk < virtual
    ):
        raise ContractError(
            "disk_gib must cover "
            "the sealed image virtual size"
        )

    return resources


def materialize_machine(
    repo_root: Path | str,
    *,
    template_id: str,
    machine_id: str,
    owner: str,
    created_at: str,
    display_name: str | None = None,
    purpose: str | None = None,
    lifecycle: str | None = None,
    device_capability: str | None = None,
    gpu_handoff_profile: str | None = None,
    network_profile: str | None = None,
    resource_profile: str | None = None,
    memory_mb: int | str | None = None,
    vcpus: int | None = None,
    disk_gib: int | None = None,
    looking_glass_mode: str = "disabled",
) -> dict[str, Any]:
    if (
        not isinstance(machine_id, str)
        or MACHINE_ID_RE.fullmatch(
            machine_id
        ) is None
    ):
        raise ContractError(
            "Machine id has an invalid format"
        )

    _, template, image = _template_document(
        repo_root,
        template_id,
    )

    if template.get("status") != "ready":
        raise ContractError(
            f"Template {template_id} is not ready"
        )

    if not _sealed_image(
        image
    ):
        raise ContractError(
            f"Template {template_id} "
            "does not reference a sealed "
            "Golden Image"
        )

    lifecycles = _enabled(
        template["lifecycles"],
        (
            "permanent",
            "disposable",
        ),
        "Template lifecycles",
    )

    devices = _enabled(
        template["device_capabilities"],
        (
            "standard",
            "vfio",
        ),
        "Template device_capabilities",
    )

    gpu_handoff_profiles = (
        _gpu_handoff_profiles(
            template,
            devices,
        )
    )

    networks = _networks(
        template,
        image,
    )

    profiles = _enabled(
        template["resource_profiles"],
        (
            "minimum",
            "balanced",
            "performance",
            "custom",
        ),
        "Template resource_profiles",
    )

    defaults = template[
        "defaults"
    ]

    selected_lifecycle = (
        lifecycle
        if lifecycle is not None
        else defaults["lifecycle"]
    )

    selected_device = (
        device_capability
        if device_capability is not None
        else defaults["device_capability"]
    )

    selected_gpu_handoff = (
        gpu_handoff_profile
        if gpu_handoff_profile is not None
        else defaults["gpu_handoff_profile"]
    )

    selected_network = (
        network_profile
        if network_profile is not None
        else defaults["network_profile"]
    )

    selected_resources = (
        resource_profile
        if resource_profile is not None
        else defaults["resource_profile"]
    )

    if selected_lifecycle not in lifecycles:
        raise ContractError(
            f"Template does not permit lifecycle "
            f"{selected_lifecycle}"
        )

    if selected_device not in devices:
        raise ContractError(
            f"Template does not permit device capability "
            f"{selected_device}"
        )

    if selected_device == "vfio":
        if selected_gpu_handoff not in gpu_handoff_profiles:
            raise ContractError(
                "Template does not permit GPU handoff "
                f"profile {selected_gpu_handoff}"
            )
    elif selected_gpu_handoff is not None:
        raise ContractError(
            "standard Machine cannot carry "
            "gpu_handoff_profile"
        )

    if selected_network not in networks:
        raise ContractError(
            f"Template does not permit network "
            f"{selected_network}"
        )

    if (
        selected_device == "vfio"
        and selected_network in GPU_HANDOFF_LADDER
        and GPU_HANDOFF_LADDER[selected_gpu_handoff]
        > GPU_HANDOFF_LADDER[selected_network]
    ):
        raise ContractError(
            f"GPU handoff profile {selected_gpu_handoff} "
            f"ranks above network {selected_network}"
        )

    if selected_resources not in profiles:
        raise ContractError(
            f"Template does not permit resource profile "
            f"{selected_resources}"
        )

    template_mode = template[
        "presentation"
    ]["looking_glass_mode"]

    if looking_glass_mode not in LOOKING_GLASS_MODES:
        raise ContractError(
            "requested Looking Glass mode "
            "is unsupported"
        )

    if looking_glass_mode != "disabled":
        if selected_device != "vfio":
            raise ContractError(
                "Looking Glass requires VFIO"
            )

        if template_mode == "disabled":
            raise ContractError(
                "Template does not permit Looking Glass"
            )

        if looking_glass_mode != template_mode:
            raise ContractError(
                "requested Looking Glass mode "
                "differs from Template capability"
            )

    resources = _resource_values(
        image,
        selected_resources,
        memory_mb=memory_mb,
        vcpus=vcpus,
        disk_gib=disk_gib,
    )

    record: dict[str, Any] = {
        "schema_version": 1,
        "id": machine_id,
        "display_name": (
            display_name
            if display_name is not None
            else machine_id
        ),
        "template": {
            "id": template["id"],
            "version": template["version"],
        },
        "image": {
            "id": image["id"],
            "sha256": image["sha256"],
        },
        "lifecycle": selected_lifecycle,
        "device_capability": selected_device,
        "gpu_handoff_profile": selected_gpu_handoff,
        "network_profile": selected_network,
        "resources": resources,
        "presentation": {
            "looking_glass_mode": (
                looking_glass_mode
            ),
            "recovery_console": template[
                "presentation"
            ][
                "recovery_console"
            ],
            "workspace_profile": template[
                "presentation"
            ][
                "workspace_profile"
            ],
        },
        "owner": owner,
        "created_at": created_at,
    }

    if purpose is not None:
        record["purpose"] = purpose

    return validate_machine_record(
        record
    )


def create_from_template(
    repo_root: Path | str,
    *,
    state_home: Path | None = None,
    **kwargs: Any,
) -> Path:
    record = materialize_machine(
        repo_root,
        **kwargs,
    )

    return create_machine(
        record,
        state_home=state_home,
    )

def project_vm_spec(
    repo_root: Path | str,
    machine: dict[str, Any],
) -> dict[str, Any]:
    """Project persistent Machine intent into the existing VM-spec adapter."""

    machine = validate_machine_record(
        machine
    )

    root = _repo_root(
        repo_root
    )

    image_id = machine[
        "image"
    ]["id"]

    image = _image(
        root,
        image_id,
    )

    if not _sealed_image(image):
        raise ContractError(
            f"Machine image {image_id} "
            "is no longer a sealed image"
        )

    if (
        image.get("sha256")
        != machine["image"]["sha256"]
    ):
        raise ContractError(
            "Machine Golden Image digest differs "
            "from the current manifest"
        )

    supports = _mapping(
        image.get("supports"),
        "image supports",
    )

    mode = machine[
        "presentation"
    ]["looking_glass_mode"]

    looking_glass = (
        mode != "disabled"
    )

    purpose = machine.get(
        "purpose"
    ) or (
        machine["display_name"]
        + " HyperLab Machine"
    )

    tags = []

    for tag in (
        "managed-machine",
        image.get("os_family"),
        image_id,
        machine["lifecycle"],
        machine["device_capability"],
        machine["network_profile"],
    ):
        if (
            isinstance(tag, str)
            and tag
            and tag not in tags
        ):
            tags.append(
                tag
            )

    spec: dict[str, Any] = {
        "schema_version": 1,
        "name": machine["id"],
        "image": image_id,
        "image_sha256": machine["image"]["sha256"],
        "lifecycle": machine["lifecycle"],
        "device_profile": machine["device_capability"],
        "network_profile": machine["network_profile"],
        "resources": dict(
            machine["resources"]
        ),
        "memory_overcommit": False,
        "autostart": False,
        "qemu_guest_agent": bool(
            supports.get(
                "qemu_guest_agent"
            )
        ),
        "looking_glass": looking_glass,
        "clipboard": False,
        "shared_folders": False,
        "usb_allowlist": [],
        "owner": machine["owner"],
        "purpose": purpose,
        "tags": tags,
        "snapshot_policy": (
            "none"
            if machine["lifecycle"]
            == "disposable"
            else "manual"
        ),
        "backup_policy": (
            "none"
            if machine["lifecycle"]
            == "disposable"
            else "manual"
        ),
    }

    gpu_handoff_profile = machine.get(
        "gpu_handoff_profile"
    )

    if gpu_handoff_profile is not None:
        spec[
            "gpu_handoff_profile"
        ] = gpu_handoff_profile

    if looking_glass:
        spec[
            "looking_glass_mode"
        ] = mode

    return spec


def write_projected_vm_spec(
    repo_root: Path | str,
    machine: dict[str, Any],
) -> str:
    """Write only the derived adapter spec; the Machine remains authority."""

    return write_spec(
        repo_root,
        project_vm_spec(
            repo_root,
            machine,
        ),
        replace=False,
    )

