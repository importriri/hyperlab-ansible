#!/usr/bin/env python3
"""Mutation tests proving the schema validator rejects dangerous contracts."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Callable

import yaml

from schema_validate import validate_repository

ROOT = Path(__file__).resolve().parents[1]


class SchemaMutationTests(unittest.TestCase):
    def with_repo(self, mutation: Callable[[Path], None]) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="privatestack-schema-") as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", ".ansible", "__pycache__"))
            mutation(copy)
            return validate_repository(copy).errors

    def assert_mutation_fails(self, mutation: Callable[[Path], None], expected: str) -> None:
        errors = self.with_repo(mutation)
        self.assertTrue(errors, "mutation unexpectedly passed")
        self.assertTrue(
            any(expected in error for error in errors),
            f"expected {expected!r}; got:\n" + "\n".join(errors),
        )

    @staticmethod
    def mutate_yaml(root: Path, relative: str, change: Callable[[dict], None]) -> None:
        path = root / relative
        data = yaml.safe_load(path.read_text())
        change(data)
        path.write_text(yaml.safe_dump(data, sort_keys=False))

    def test_baseline_is_green(self) -> None:
        result = validate_repository(ROOT)
        self.assertEqual([], result.errors)

    def test_negative_vcpus_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "vm-specs/debian-dev.yml", lambda d: d["resources"].update(vcpus=-4)),
            "resources.vcpus=-4 is below minimum 1",
        )

    def test_zero_image_size_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "images/debian.yml", lambda d: d.update(virtual_size_gib=0)),
            "virtual_size_gib=0 is below minimum 1",
        )

    def test_disk_smaller_than_base_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "vm-specs/debian-dev.yml", lambda d: d["resources"].update(disk_gib=1)),
            "disk_gib=1 is smaller than image virtual_size_gib=20",
        )

    def test_looking_glass_without_host_pin_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "images/win11clean.yml", lambda d: d.update(looking_glass_host_build_required=None)),
            "Looking Glass requires a non-null host build pin",
        )

    def test_secure_boot_without_uefi_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "images/win11dirty.yml", lambda d: d["requires"].update(uefi=False)),
            "requires.secure_boot implies requires.uefi",
        )

    def test_guest_agent_request_without_image_support_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "images/debian.yml", lambda d: d["supports"].update(qemu_guest_agent=False)),
            "QEMU Guest Agent requested but the image does not support it",
        )

    def test_duplicate_tags_are_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "vm-specs/debian-dev.yml", lambda d: d.update(tags=["linux", "linux"])),
            "tags contains duplicate item",
        )

    def test_non_mapping_document_is_rejected_cleanly(self) -> None:
        def mutation(root: Path) -> None:
            (root / "images/debian.yml").write_text("- not\n- a\n- mapping\n")

        self.assert_mutation_fails(mutation, "document root must be a mapping")

    def test_singleton_cannot_have_two_specs(self) -> None:
        def mutation(root: Path) -> None:
            original = yaml.safe_load((root / "vm-specs/win11clean-valley.yml").read_text())
            original["name"] = "win11clean-second"
            (root / "vm-specs/win11clean-second.yml").write_text(yaml.safe_dump(original, sort_keys=False))

        self.assert_mutation_fails(mutation, "instance_policy singleton is referenced by multiple specs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
