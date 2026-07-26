#!/usr/bin/env python3
"""Mutation tests for the non-schema pipeline contract."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Callable

import yaml

from static_contract import collect_errors

ROOT = Path(__file__).resolve().parents[1]


class ContractMutationTests(unittest.TestCase):
    def with_repo(self, mutation: Callable[[Path], None]) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="privatestack-contract-") as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", ".ansible", "__pycache__"))
            mutation(copy)
            return collect_errors(copy)

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
        self.assertEqual([], collect_errors(ROOT))

    def test_looking_glass_needs_kvm_host(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "group_vars/all/bricks.yml", lambda d: d["brick_requires"].update(looking_glass=["desktop"])),
            "Looking Glass needs desktop and kvm_host",
        )

    def test_unknown_prerequisite_is_rejected(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "group_vars/all/bricks.yml", lambda d: d["brick_requires"].update(looking_glass=["desktop", "kvm_host", "typo"])),
            "looking_glass requires an unknown brick",
        )

    def test_guard_must_reject_unknown_brick_name(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "roles/brick_guard/tasks/main.yml"
            path.write_text(path.read_text().replace("brick_guard_brick in brick_requires", "true"))

        self.assert_mutation_fails(mutation, "brick_guard must reject an unknown brick name")

    def test_vm_contract_must_not_reuse_host_profile(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "schemas/vm-spec.v1.yml"
            path.write_text(path.read_text().replace("device_profile", "host_profile"))

        self.assert_mutation_fails(mutation, "VM specs must use device_profile only")

    def test_unknown_hardware_rescue_must_stay_narrow(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "roles/hardware_probe/tasks/main.yml"
            path.write_text(path.read_text().replace("  when: host_profile == 'auto'\n  block:", "  block:", 1))

        self.assert_mutation_fails(mutation, "unknown-machine rescue must be limited to automatic selection")

    def test_memory_ratio_is_part_of_host_data(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(root, "group_vars/all/hardware.yml", lambda d: d["host_profiles"]["nitro-3060"]["memory"].pop("standard_overcommit_ratio")),
            "nitro-3060 must declare the complete memory budget contract",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
