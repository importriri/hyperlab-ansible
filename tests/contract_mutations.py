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

    def test_reviewed_runtime_identity_cannot_fall_back_to_the_sentinel(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(
                root,
                "host_vars/localhost.yml",
                lambda d: d.update(hyperlab_swtpm_user_declared="__REQUIRED_FROM_HARDWARE__"),
            ),
            "localhost must declare the reviewed Arch libvirt and swtpm identities",
        )

    def test_swtpm_belongs_to_the_kvm_foundation(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(
                root,
                "roles/kvm_host/defaults/main.yml",
                lambda d: d["kvm_host_packages"].remove("swtpm"),
            ),
            "KVM foundation must create the swtpm runtime identity before image_store",
        )

    def test_spice_audio_module_is_a_guest_dependency(self) -> None:
        self.assert_mutation_fails(
            lambda root: self.mutate_yaml(
                root,
                "group_vars/all/guest.yml",
                lambda d: d["guest_required_packages"].remove("qemu-audio-spice"),
            ),
            "SPICE guests require the complete split QEMU UI, chardev and audio modules",
        )

    def test_managed_disk_must_refuse_dac_relabel(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "roles/guest/templates/domain.xml.j2"
            path.write_text(
                path.read_text().replace(
                    '        <seclabel model="dac" relabel="no"/>\n',
                    "",
                )
            )

        self.assert_mutation_fails(
            mutation,
            "managed disks must refuse libvirt DAC relabel of sealed backing chains",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
