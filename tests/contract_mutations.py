#!/usr/bin/env python3
"""Mutation tests for the non-schema pipeline contract."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable

import yaml

from ci_verify_parity_contract import collect_errors as parity_errors
from static_contract import collect_errors
from verify_render_selection_contract import collect_errors as render_selection_errors

ROOT = Path(__file__).resolve().parents[1]
CI = ".github/workflows/ci.yml"
SHELL_CHECK = "sh tools/shell-tests/run.sh"
PALETTE_AND_CHOICES = (
    "python3 tools/palette/audit_palette.py tools/palette/palette.yml",
    "python3 tools/palette/verify_surfaces.py roles/host_desktop_sway/files/palette",
    "python3 tools/choices/choices.py check",
    "python3 tools/choices/test_choices.py",
    "python3 tools/choices/test_consistency.py",
)


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

    def test_looking_glass_kvmfr_reload_must_stay_runtime_guarded(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "roles/looking_glass/tasks/main.yml"
            source = path.read_text()
            path.write_text(
                source.replace(
                    "when: looking_glass_kvmfr_reload_required | bool\n"
                    "  community.general.modprobe:\n"
                    "    name: kvmfr\n"
                    "    state: absent",
                    "community.general.modprobe:\n"
                    "    name: kvmfr\n"
                    "    state: absent",
                    1,
                )
            )

        self.assert_mutation_fails(
            mutation,
            "kvmfr reload must be explicit and runtime-gated",
        )

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
            path.write_text(path.read_text().replace(
                "- name: Leave the evidence needed to add an unknown machine\n      when: host_profile == 'auto'\n",
                "- name: Leave the evidence needed to add an unknown machine\n", 1))

        self.assert_mutation_fails(mutation, "unknown-machine rescue must be limited to automatic selection")

    def test_auto_never_considers_a_profile_without_gpu(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "roles/hardware_probe/tasks/select.yml"
            path.write_text(path.read_text().replace("         | rejectattr('value.gpu_passthrough', 'defined')\n", "", 1))

        self.assert_mutation_fails(mutation, "automatic selection must never consider a profile without GPU passthrough")

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

    def test_spice_audio_needs_a_managed_guest_sound_device(self) -> None:
        def mutation(root: Path) -> None:
            path = root / "roles/guest/templates/domain.xml.j2"
            path.write_text(
                path.read_text().replace(
                    '    <sound model="ich9">\n'
                    '      <codec type="output"/>\n'
                    '      <audio id="1"/>\n'
                    '    </sound>\n',
                    "",
                )
            )

        self.assert_mutation_fails(
            mutation,
            "managed SPICE domains must expose an ICH9 playback-only sound device",
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


    def test_looking_glass_captured_press_fix_is_guarded(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="privatestack-contract-"
        ) as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(
                ROOT,
                copy,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".ansible",
                    "__pycache__",
                ),
            )

            path = (
                copy
                / "roles/looking_glass/files/client-captured-button-press.patch"
            )
            source = path.read_text(encoding="utf-8")
            fixed = (
                "if (!core_inputEnabled() || "
                "(!g_cursor.grab && !g_cursor.inView))"
            )
            self.assertIn(fixed, source)
            path.write_text(
                source.replace(
                    fixed,
                    "if (!core_inputEnabled() || !g_cursor.inView)",
                    1,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "tests/looking_glass_client_input_contract.py",
                ],
                cwd=copy,
                capture_output=True,
                text=True,
                check=False,
            )

            output = result.stdout + result.stderr
            self.assertNotEqual(
                result.returncode,
                0,
                "mutation unexpectedly passed",
            )
            self.assertIn(
                "client input patch SHA-256 differs",
                output,
            )


    def test_runtime_guest_inventory_must_disable_ssh_pseudo_tty(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="privatestack-contract-"
        ) as tmp:
            copy = Path(tmp) / "repo"
            shutil.copytree(
                ROOT,
                copy,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".ansible",
                    "__pycache__",
                ),
            )

            path = copy / "playbooks/vm-guest-inventory.yml"
            source = path.read_text(encoding="utf-8")
            marker = "              'ansible_ssh_use_tty=false',\n"
            self.assertIn(marker, source)

            path.write_text(
                source.replace(marker, "", 1),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "tests/guest_inventory_contract.py",
                ],
                cwd=copy,
                capture_output=True,
                text=True,
                check=False,
            )

            output = result.stdout + result.stderr
            self.assertNotEqual(
                result.returncode,
                0,
                "mutation unexpectedly passed",
            )
            self.assertIn(
                "runtime guest inventory must disable SSH pseudo-TTY allocation",
                output,
            )


class CiVerifyParityMutationTests(unittest.TestCase):
    """Each break edits a copy of ci.yml or verify.sh and must turn the parity contract red."""

    @staticmethod
    def replace_once(path: Path, old: str, new: str) -> None:
        source = path.read_text(encoding="utf-8")
        if source.count(old) != 1:
            raise AssertionError(f"{old!r} occurs {source.count(old)} times in {path.name}, not once")
        path.write_text(source.replace(old, new), encoding="utf-8")

    def assert_parity_fails(self, mutation: Callable[[Path], None], expected: str) -> None:
        with tempfile.TemporaryDirectory(prefix="privatestack-parity-") as tmp:
            copy = Path(tmp)
            (copy / CI).parent.mkdir(parents=True)
            shutil.copy2(ROOT / CI, copy / CI)
            shutil.copy2(ROOT / "verify.sh", copy / "verify.sh")
            mutation(copy)
            errors = parity_errors(copy)
        self.assertTrue(errors, "mutation unexpectedly passed")
        self.assertTrue(
            any(expected in error for error in errors),
            f"expected {expected!r}; got:\n" + "\n".join(errors),
        )

    def test_baseline_is_green(self) -> None:
        self.assertEqual([], parity_errors(ROOT))

    def test_ci_duplicate_yaml_key_is_refused(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        run: 'true'\n        run: {SHELL_CHECK}\n",
            ),
            "duplicate YAML key",
        )

    def test_ci_duplicate_step_id_is_refused(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        id: structural_contracts\n        run: {SHELL_CHECK}\n",
            ),
            "duplicate step id",
        )

    def test_redirected_entrypoints_are_refused(self) -> None:
        for name in (CI, "verify.sh"):
            with self.subTest(name=name):
                def mutation(root: Path, name: str = name) -> None:
                    path = root / name
                    target = path.with_suffix(".original")
                    path.rename(target)
                    path.symlink_to(target.name)

                self.assert_parity_fails(mutation, "entrypoint must be a regular, unredirected file")

    def test_ci_unmodelled_shell_is_refused(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        shell: {{invalid: bash}}\n        run: {SHELL_CHECK}\n",
            ),
            "uses shell",
        )

    def test_ci_shell_step_kept_only_as_its_name_and_a_comment(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        run: |\n          # {SHELL_CHECK}\n          echo '{SHELL_CHECK}'\n",
            ),
            f"CI did not run {SHELL_CHECK}",
        )

    def test_ci_shell_check_behind_an_unreachable_branch(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        run: if false; then {SHELL_CHECK}; fi\n",
            ),
            f"CI did not run {SHELL_CHECK}",
        )

    def test_ci_shell_check_moved_into_the_toolchain_step(self) -> None:
        def mutation(root: Path) -> None:
            self.replace_once(root / CI, f"        run: {SHELL_CHECK}\n", "        run: 'true'\n")
            self.replace_once(
                root / CI,
                "          test -x /usr/lib/qt6/bin/qmlscene\n",
                f"          test -x /usr/lib/qt6/bin/qmlscene\n          {SHELL_CHECK}\n",
            )

        self.assert_parity_fails(mutation, f"CI did not run {SHELL_CHECK}")

    def test_ci_drops_any_palette_or_choices_command(self) -> None:
        for command in PALETTE_AND_CHOICES:
            with self.subTest(command=command):
                self.assert_parity_fails(
                    lambda root, command=command: self.replace_once(
                        root / CI, f"          {command}\n", ""
                    ),
                    f"CI did not run {command}",
                )

    def test_a_required_command_may_not_run_twice(self) -> None:
        command = PALETTE_AND_CHOICES[0]
        for name, prefix, where in ((CI, "          ", "CI"), ("verify.sh", "run ", "verify.sh")):
            with self.subTest(name=name):
                self.assert_parity_fails(
                    lambda root, name=name, prefix=prefix: self.replace_once(
                        root / name, f"{prefix}{command}\n", f"{prefix}{command}\n" * 2
                    ),
                    f"{where} ran {command} 2 times",
                )

    def test_ci_palette_argument_changes(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                "audit_palette.py tools/palette/palette.yml\n",
                "audit_palette.py tools/palette/palette.yaml\n",
            ),
            f"CI did not run {PALETTE_AND_CHOICES[0]}",
        )

    def test_ci_surfaces_argument_changes(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                "verify_surfaces.py roles/host_desktop_sway/files/palette\n",
                "verify_surfaces.py roles/host_desktop_sway/files\n",
            ),
            f"CI did not run {PALETTE_AND_CHOICES[1]}",
        )

    def test_matching_wrong_arguments_in_both_paths_are_refused(self) -> None:
        def mutation(root: Path) -> None:
            for name in (CI, "verify.sh"):
                self.replace_once(
                    root / name,
                    "audit_palette.py tools/palette/palette.yml\n",
                    "audit_palette.py tools/palette/palette.yaml\n",
                )

        self.assert_parity_fails(mutation, f"CI did not run {PALETTE_AND_CHOICES[0]}")

    def test_ci_palette_step_may_not_continue_on_error(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                "      - name: Palette and open choices\n",
                "      - name: Palette and open choices\n        continue-on-error: true\n",
            ),
            "sets 'continue-on-error'",
        )

    def test_ci_shell_step_may_not_wait_for_a_manual_event(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                "      - name: Shell structure (no display required)\n",
                "      - name: Shell structure (no display required)\n"
                "        if: github.event_name == 'workflow_dispatch'\n",
            ),
            "sets 'if'",
        )

    def test_ci_must_still_run_on_pull_requests(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(root / CI, "  pull_request:\n", ""),
            "CI must run on every push and every pull request, unfiltered",
        )

    def test_ci_validation_job_may_not_be_optional(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI, "  validate:\n", "  validate:\n    continue-on-error: true\n"
            ),
            "the validate job sets 'continue-on-error'",
        )

    def test_ci_discards_a_failed_child_status(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        run: |\n          {SHELL_CHECK} &\n          wait || true\n",
            ),
            f"CI succeeded while {SHELL_CHECK} failed",
        )

    def test_ci_discarded_status_hides_a_failure(self) -> None:
        command = PALETTE_AND_CHOICES[4]
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI, f"          {command}\n", f"          {command} || true\n"
            ),
            f"CI succeeded while {command} failed",
        )

    def test_ci_pipe_to_tee_hides_a_failure(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / CI,
                f"        run: {SHELL_CHECK}\n",
                f"        run: {SHELL_CHECK} | tee shell-tests.log\n",
            ),
            f"CI succeeded while {SHELL_CHECK} failed",
        )

    def test_ci_later_success_hides_a_failure(self) -> None:
        command = PALETTE_AND_CHOICES[0]

        def mutation(root: Path) -> None:
            self.replace_once(
                root / CI, f"          {command}\n", f"          set +e\n          {command}\n"
            )
            self.replace_once(
                root / CI,
                f"          {PALETTE_AND_CHOICES[4]}\n",
                f"          {PALETTE_AND_CHOICES[4]}\n          echo done\n",
            )

        self.assert_parity_fails(mutation, f"CI succeeded while {command} failed")

    def test_ci_six_checks_after_a_failing_step_are_skipped(self) -> None:
        def mutation(root: Path) -> None:
            source = (root / CI).read_text(encoding="utf-8")
            start = source.index("      # The same commands as verify.sh levels 0f and 0g")
            end = source.index("      - name: Lint every Python file (repo ruleset)\n")
            block = source[start:end]
            self.replace_once(root / CI, block, "")
            self.replace_once(
                root / CI,
                "      - name: Refusal suites (discovered)\n",
                block + "      - name: Refusal suites (discovered)\n",
            )

        self.assert_parity_fails(
            mutation, "when python 'tests/*_contract.py' failed"
        )

    def test_verify_discarded_status_hides_a_failure(self) -> None:
        command = PALETTE_AND_CHOICES[2]
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                f"run {command}\n",
                f"{command} >/dev/null 2>&1 || true\n",
            ),
            f"verify.sh exited 0 while {command} failed",
        )

    def test_verify_drops_the_shell_check(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(root / "verify.sh", f"run {SHELL_CHECK}\n", ""),
            "CI and verify.sh run different tool checks",
        )

    def test_verify_gains_a_check_ci_does_not_run(self) -> None:
        self.assert_parity_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                f"run {PALETTE_AND_CHOICES[4]}\n",
                f"run {PALETTE_AND_CHOICES[4]}\nrun python3 tools/palette/verify_output.py\n",
            ),
            "CI and verify.sh run different tool checks",
        )



class VerifyRenderSelectionMutationTests(unittest.TestCase):
    """Each break edits a copy of verify.sh and must turn the render selection contract red."""

    replace_once = staticmethod(CiVerifyParityMutationTests.replace_once)

    def assert_selection_fails(self, mutation: Callable[[Path], None], expected: str) -> None:
        with tempfile.TemporaryDirectory(prefix="privatestack-render-selection-") as tmp:
            copy = Path(tmp)
            shutil.copy2(ROOT / "verify.sh", copy / "verify.sh")
            mutation(copy)
            errors = render_selection_errors(copy)
        self.assertTrue(errors, "mutation unexpectedly passed")
        self.assertTrue(
            any(expected in error for error in errors),
            f"expected {expected!r}; got:\n" + "\n".join(errors),
        )

    def test_baseline_is_green(self) -> None:
        self.assertEqual([], render_selection_errors(ROOT))

    def test_no_credentials_returns_before_the_render_suite(self) -> None:
        self.assert_selection_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                "        render_select=(--skip-tags privileged)\n        render_judge_missing=1\n",
                "        fail=1\n        return\n",
            ),
            "partial success (pipe): render suite ran [], expected",
        )

    def test_partial_run_must_skip_only_the_privileged_tag(self) -> None:
        self.assert_selection_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                "        render_select=(--skip-tags privileged)\n",
                "        render_select=()\n",
            ),
            "partial success (pipe): render suite ran "
            "['ansible-playbook -i inventory.ini tests/render.yml --extra-vars",
        )

    def test_full_runs_may_not_skip_the_judge(self) -> None:
        breaks = (
            (
                "local -a render_select=()\n",
                "local -a render_select=(--skip-tags privileged)\n",
                "full success with a supplied file (pipe): render suite ran",
            ),
            (
                'become_args=(--become-password-file "${PRIVATESTACK_BECOME_PASSWORD_FILE}")\n',
                'become_args=(--become-password-file "${PRIVATESTACK_BECOME_PASSWORD_FILE}")\n'
                "        render_select=(--skip-tags privileged)\n",
                "full success with a supplied file (pipe): render suite ran",
            ),
            (
                "        become_args=()\n",
                "        become_args=()\n        render_select=(--skip-tags privileged)\n",
                "passwordless full success (pipe): render suite ran",
            ),
        )
        for old, new, expected in breaks:
            with self.subTest(new=new):
                self.assert_selection_fails(
                    lambda root, old=old, new=new: self.replace_once(root / "verify.sh", old, new),
                    expected,
                )

    def test_partial_render_failure_may_not_be_swallowed(self) -> None:
        breaks = (
            (
                '        run ansible-playbook "${become_args[@]}"',
                '        ansible-playbook "${become_args[@]}"',
                "partial render failure (pipe): verdict ['VERIFICATION INCOMPLETE",
            ),
            (
                '            echo "   FAIL"\n            fail=1\n',
                '            echo "   FAIL"\n',
                "partial render failure (terminal): verdict ['VERIFICATION INCOMPLETE",
            ),
        )
        for old, new, expected in breaks:
            with self.subTest(old=old):
                self.assert_selection_fails(
                    lambda root, old=old, new=new: self.replace_once(root / "verify.sh", old, new),
                    expected,
                )

    def test_partial_success_may_not_print_all_green(self) -> None:
        self.assert_selection_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                'if [ "${fail}" -eq 0 ] && [ "${render_judge_missing}" -eq 0 ]; then\n',
                'if [ "${fail}" -eq 0 ]; then\n',
            ),
            "partial success (pipe): verdict ['ALL GREEN - ready to commit.']",
        )

    def test_failure_may_not_be_reported_as_the_missing_judge(self) -> None:
        self.assert_selection_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                'elif [ "${fail}" -eq 0 ]; then\n',
                'elif [ "${render_judge_missing}" -eq 1 ]; then\n',
            ),
            "partial run with a lint failure (pipe): verdict ['VERIFICATION INCOMPLETE",
        )

    def test_partial_run_must_name_the_missing_judge(self) -> None:
        self.assert_selection_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                '        echo "   NOT RUN - the privileged nft -c judge of tests/render.yml (no sudo credentials)"\n',
                "        :\n",
            ),
            "partial success (pipe): level 2b reports the nft -c judge as not run 0 times",
        )

    def test_unreadable_supplied_file_may_not_fall_back(self) -> None:
        self.assert_selection_fails(
            lambda root: self.replace_once(
                root / "verify.sh",
                'if [ -n "${PRIVATESTACK_BECOME_PASSWORD_FILE:-}" ]; then\n',
                'if [ -r "${PRIVATESTACK_BECOME_PASSWORD_FILE:-}" ]; then\n',
            ),
            "supplied file missing (pipe): render suite ran "
            "['ansible-playbook -i inventory.ini tests/render.yml --skip-tags privileged",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
