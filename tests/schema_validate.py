#!/usr/bin/env python3
"""Validate image manifests and VM specs against versioned YAML schemas.

This validator is deliberately static: it never talks to libvirt and never
claims a VM will fit on a host. Runtime capacity belongs to M2 (ADR 0007).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SECRET_HINTS = ("password", "passwd", "token", "secret", "api_key", "private_key")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    image_count: int = 0
    spec_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


class RepositoryValidator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.result = ValidationResult()
        self.valid_domains: list[str] = []

    def fail(self, where: str, message: str) -> None:
        self.result.errors.append(f"{where}: {message}")

    def relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def load_yaml(self, path: Path, *, mapping: bool = True) -> Any:
        where = self.relative(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.fail(where, "file does not exist")
            return {} if mapping else None
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            self.fail(where, f"cannot parse YAML: {exc}")
            return {} if mapping else None
        if mapping and not isinstance(data, dict):
            self.fail(where, "document root must be a mapping")
            return {}
        return data

    def domains(self) -> list[str]:
        data = self.load_yaml(self.root / "group_vars/all/networks.yml")
        domains = data.get("network_domains", [])
        if not isinstance(domains, list):
            self.fail("group_vars/all/networks.yml", "network_domains must be a list")
            return []
        names: list[str] = []
        for index, domain in enumerate(domains):
            if not isinstance(domain, dict) or not isinstance(domain.get("name"), str):
                self.fail("group_vars/all/networks.yml", f"network_domains[{index}] needs a string name")
                continue
            names.append(domain["name"])
        return names

    @staticmethod
    def duplicate_items(items: Iterable[Any]) -> list[Any]:
        duplicates: list[Any] = []
        seen: set[str] = set()
        for item in items:
            marker = yaml.safe_dump(item, sort_keys=True)
            if marker in seen and item not in duplicates:
                duplicates.append(item)
            seen.add(marker)
        return duplicates

    def check_value(self, where: str, key: str, value: Any, rule: dict[str, Any]) -> None:
        if value is None:
            if not rule.get("nullable", False):
                self.fail(where, f"{key} is null and the schema does not allow it")
            return
        kind = rule.get("type", "str")
        if kind == "map":
            if not isinstance(value, dict):
                self.fail(where, f"{key} must be a mapping")
                return
            fields = rule.get("fields", {})
            for missing in sorted(set(fields) - set(value)):
                self.fail(where, f"{key}.{missing} is required")
            for subkey, subvalue in value.items():
                if subkey not in fields:
                    self.fail(where, f"{key}.{subkey} is not in the schema")
                    continue
                self.check_value(where, f"{key}.{subkey}", subvalue, fields[subkey])
            return
        if kind == "list":
            if not isinstance(value, list):
                self.fail(where, f"{key} must be a list")
                return
            if "min_items" in rule and len(value) < rule["min_items"]:
                self.fail(where, f"{key} needs at least {rule['min_items']} item(s)")
            if rule.get("unique_items"):
                duplicates = self.duplicate_items(value)
                if duplicates:
                    self.fail(where, f"{key} contains duplicate item(s): {duplicates!r}")
            for index, item in enumerate(value):
                if rule.get("of") == "str" and not isinstance(item, str):
                    self.fail(where, f"{key}[{index}] must be a string")
                    continue
                if rule.get("of") == "str" and not item:
                    self.fail(where, f"{key}[{index}] must not be empty")
                if rule.get("domain") and item not in self.valid_domains:
                    self.fail(where, f"{key}[{index}]={item!r} is not a declared network domain")
            return
        if kind == "int_or_auto":
            if value == "auto":
                return
            if not isinstance(value, int) or isinstance(value, bool):
                self.fail(where, f"{key} must be an integer or the string 'auto'")
                return
            self.check_numeric_constraints(where, key, value, rule)
            return
        expected_types = {"int": int, "str": str, "bool": bool, "number": (int, float)}
        if kind not in expected_types:
            self.fail(where, f"schema uses unsupported type {kind!r} for {key}")
            return
        if kind in {"int", "number"} and isinstance(value, bool):
            self.fail(where, f"{key} must be {kind}, not a boolean")
            return
        if not isinstance(value, expected_types[kind]):
            self.fail(where, f"{key} must be {kind}")
            return
        if "enum" in rule and value not in rule["enum"]:
            self.fail(where, f"{key}={value!r} is not one of {rule['enum']}")
        if rule.get("domain") and value not in self.valid_domains:
            self.fail(where, f"{key}={value!r} is not a declared network domain")
        if "pattern" in rule and isinstance(value, str) and re.fullmatch(rule["pattern"], value) is None:
            self.fail(where, f"{key}={value!r} does not match {rule['pattern']}")
        if "min_length" in rule and isinstance(value, str) and len(value) < rule["min_length"]:
            self.fail(where, f"{key} must be at least {rule['min_length']} character(s)")
        if kind in {"int", "number"}:
            self.check_numeric_constraints(where, key, value, rule)

    def check_numeric_constraints(self, where: str, key: str, value: int | float, rule: dict[str, Any]) -> None:
        if "min" in rule and value < rule["min"]:
            self.fail(where, f"{key}={value} is below minimum {rule['min']}")
        if "max" in rule and value > rule["max"]:
            self.fail(where, f"{key}={value} exceeds maximum {rule['max']}")

    def scan_sensitive_values(self, where: str, node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_path = f"{path}.{key}" if path else str(key)
                if any(hint in str(key).lower() for hint in SECRET_HINTS):
                    self.fail(where, f"{key_path} looks like a secret; secrets do not belong in Git")
                self.scan_sensitive_values(where, value, key_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                self.scan_sensitive_values(where, value, f"{path}[{index}]")
        elif isinstance(node, str) and node.startswith("/home/"):
            self.fail(where, f"{path} carries an absolute personal path")

    def check_document(self, path: Path, document: dict[str, Any], schema: dict[str, Any]) -> None:
        where = self.relative(path)
        if not document:
            return
        required = schema.get("fields", {})
        optional = schema.get("optional", {})
        for missing in sorted(set(required) - set(document)):
            self.fail(where, f"{missing} is required")
        for key, value in document.items():
            rule = required.get(key) or optional.get(key)
            if rule is None:
                self.fail(where, f"{key} is not in schema {schema.get('kind')} v{schema.get('schema_version')}")
                continue
            self.check_value(where, key, value, rule)
        self.scan_sensitive_values(where, document)

    def validate_manifest_policy(self, image_id: str, image: dict[str, Any], client_build: str) -> None:
        where = f"images/{image_id}.yml"
        status = image.get("status")
        if status == "sealed":
            if not image.get("sha256"):
                self.fail(where, "a sealed image must carry its sha256")
            if image.get("source_type") != "local" and not image.get("source_url"):
                self.fail(where, "a sealed non-local image must name its source_url")
        if status != "sealed" and image.get("looking_glass_host_build_observed") is not None:
            self.fail(where, "an unsealed image cannot claim an observed Looking Glass host build")
        if image.get("contains_personal_data") and not image.get("private"):
            self.fail(where, "personal data implies private: true")
        if image.get("contains_personal_data") and image.get("generalized"):
            self.fail(where, "a personal master cannot also claim to be generalized")
        if image.get("contains_personal_data") and image.get("instance_policy") != "singleton":
            self.fail(where, "a personal master must use instance_policy: singleton")
        if image.get("licensing", {}).get("redistributable") and image.get("private"):
            self.fail(where, "private and redistributable contradict each other")
        virtual_size = image.get("virtual_size_gib")
        minimum_size = image.get("minimum_size_gib")
        if isinstance(virtual_size, int) and isinstance(minimum_size, int) and minimum_size > virtual_size:
            self.fail(where, "minimum_size_gib cannot exceed virtual_size_gib")
        supports = image.get("supports", {})
        if not supports.get("standard") and not supports.get("vfio"):
            self.fail(where, "at least one of supports.standard or supports.vfio must be true")
        requires = image.get("requires", {})
        if requires.get("secure_boot") and not requires.get("uefi"):
            self.fail(where, "requires.secure_boot implies requires.uefi")
        defaults = image.get("defaults", {})
        allowlist = image.get("network_allowlist") or []
        if allowlist and defaults.get("network_profile") not in allowlist:
            self.fail(where, "the default network is not in the image allowlist")
        default_device = defaults.get("device_profile")
        if default_device in {"standard", "vfio"} and not supports.get(default_device):
            self.fail(where, f"defaults to {default_device} but does not declare support for it")
        if image.get("instance_policy") == "singleton" and defaults.get("lifecycle") != "permanent":
            self.fail(where, "a singleton image must default to lifecycle: permanent")
        required_build = image.get("looking_glass_host_build_required")
        observed_build = image.get("looking_glass_host_build_observed")
        if required_build and required_build != client_build:
            self.fail(where, f"required Looking Glass host build {required_build} != client {client_build}")
        if observed_build and not required_build:
            self.fail(where, "an observed Looking Glass build needs a required build pin")
        if observed_build and observed_build != required_build:
            self.fail(where, f"observed Looking Glass build {observed_build} != required {required_build}")
        if status == "sealed" and required_build and not observed_build:
            self.fail(where, "a sealed Looking Glass image must record the observed host build")

    def validate_spec_policy(self, path: Path, spec: dict[str, Any], image: dict[str, Any], client_build: str) -> None:
        where = self.relative(path)
        network = spec.get("network_profile")
        allowlist = image.get("network_allowlist") or []
        if allowlist and network not in allowlist:
            self.fail(where, f"{network} is not in the allowlist of image {spec.get('image')}")
        device = spec.get("device_profile")
        supports = image.get("supports", {})
        if device in {"standard", "vfio"} and not supports.get(device):
            self.fail(where, f"{device} requested, image does not support it")
        if device == "vfio" and spec.get("memory_overcommit"):
            self.fail(where, "overcommit on vfio is forbidden")
        if spec.get("qemu_guest_agent") and not supports.get("qemu_guest_agent"):
            self.fail(where, "QEMU Guest Agent requested but the image does not support it")
        if spec.get("looking_glass"):
            if device != "vfio":
                self.fail(where, "Looking Glass requires device_profile: vfio")
            if not supports.get("vfio"):
                self.fail(where, "Looking Glass requires an image with VFIO support")
            required_build = image.get("looking_glass_host_build_required")
            observed_build = image.get("looking_glass_host_build_observed")
            if not required_build:
                self.fail(where, "Looking Glass requires a non-null host build pin in the image manifest")
            elif required_build != client_build:
                self.fail(where, f"image host build {required_build} != client {client_build}")
            if image.get("status") == "sealed" and observed_build != required_build:
                self.fail(where, "sealed Looking Glass image lacks matching observed host-build evidence")
        lifecycle = spec.get("lifecycle")
        if lifecycle == "disposable" and image.get("contains_personal_data"):
            self.fail(where, "a personal master cannot back a disposable VM")
        if image.get("instance_policy") == "singleton" and lifecycle != "permanent":
            self.fail(where, "a singleton image may only back a permanent VM")
        if network in {"dirty", "lab"}:
            for switch in ("clipboard", "shared_folders"):
                if spec.get(switch):
                    self.fail(where, f"{switch} must stay off on {network}")
        resources = spec.get("resources", {})
        memory = resources.get("memory_mb")
        floor = image.get("min_memory_mb")
        if isinstance(memory, int) and isinstance(floor, int) and memory < floor:
            self.fail(where, f"memory_mb={memory} is below image floor {floor}")
        disk = resources.get("disk_gib")
        image_virtual = image.get("virtual_size_gib")
        if isinstance(disk, int) and isinstance(image_virtual, int) and disk < image_virtual:
            self.fail(where, f"disk_gib={disk} is smaller than image virtual_size_gib={image_virtual}")

    def validate(self) -> ValidationResult:
        self.valid_domains = self.domains()
        image_schema = self.load_yaml(self.root / "schemas/image-manifest.v1.yml")
        spec_schema = self.load_yaml(self.root / "schemas/vm-spec.v1.yml")
        looking_defaults = self.load_yaml(self.root / "roles/looking_glass/defaults/main.yml")
        client_build = looking_defaults.get("looking_glass_build", "")
        if not isinstance(client_build, str) or not client_build:
            self.fail("roles/looking_glass/defaults/main.yml", "looking_glass_build must be a non-empty string")
        images: dict[str, dict[str, Any]] = {}
        for path in sorted((self.root / "images").glob("*.yml")):
            document = self.load_yaml(path)
            self.check_document(path, document, image_schema)
            image_id = document.get("id", path.stem) if isinstance(document, dict) else path.stem
            if image_id in images:
                self.fail(self.relative(path), f"duplicate image id {image_id!r}")
            images[image_id] = document
            if document.get("id") != path.stem:
                self.fail(self.relative(path), "id must equal the file name")
        self.result.image_count = len(images)
        for image_id, image in images.items():
            self.validate_manifest_policy(image_id, image, client_build)
        singleton_references: dict[str, list[str]] = {}
        spec_paths = sorted((self.root / "vm-specs").glob("*.yml"))
        self.result.spec_count = len(spec_paths)
        for path in spec_paths:
            document = self.load_yaml(path)
            self.check_document(path, document, spec_schema)
            where = self.relative(path)
            if document.get("name") != path.stem:
                self.fail(where, "name must equal the file name")
            image_id = document.get("image", "")
            image = images.get(image_id)
            if image is None:
                self.fail(where, f"image {image_id!r} has no manifest")
                continue
            self.validate_spec_policy(path, document, image, client_build)
            if image.get("instance_policy") == "singleton":
                singleton_references.setdefault(image_id, []).append(document.get("name", path.stem))
        for image_id, names in singleton_references.items():
            if len(names) > 1:
                self.fail(f"images/{image_id}.yml", f"instance_policy singleton is referenced by multiple specs: {', '.join(names)}")
        return self.result


def validate_repository(root: Path = DEFAULT_ROOT) -> ValidationResult:
    return RepositoryValidator(root).validate()


def main() -> int:
    result = validate_repository()
    if not result.ok:
        print("SCHEMA VALIDATION FAILED", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"schemas: OK ({result.image_count} images, {result.spec_count} specs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
