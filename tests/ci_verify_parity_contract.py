#!/usr/bin/env python3
"""CI runs the shell, palette and choices checks that verify.sh runs.

verify.sh levels 0f and 0g ran six checks that the CI workflow never ran
(problems/ci-skipped-shell-palette-and-choices.md). This contract parses
.github/workflows/ci.yml and runs the validate job's run blocks the way the
runner does, then runs verify.sh, both in a temporary checkout where every
tool they call is a recording stub. Both must run the six checks below with
the same arguments, and both must fail when any one of them fails.

The fixture reaches no sudo, package manager or network: the toolchain step
is left out by its id, and PATH holds only the stubs and a few file
utilities, so anything else a run block calls is not found and fails.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = Path(".github/workflows/ci.yml")
VERIFY = Path("verify.sh")
JOB = "validate"
TOOLCHAIN = "toolchain"

# The six checks of verify.sh levels 0f and 0g, written out here rather than
# read from either file, so that an edit to both cannot change what is
# required.
EXPECTED: tuple[tuple[str, ...], ...] = (
    ("sh", "tools/shell-tests/run.sh"),
    ("python3", "tools/palette/audit_palette.py", "tools/palette/palette.yml"),
    (
        "python3",
        "tools/palette/verify_surfaces.py",
        "roles/host_desktop_sway/files/palette",
    ),
    ("python3", "tools/choices/choices.py", "check"),
    ("python3", "tools/choices/test_choices.py"),
    ("python3", "tools/choices/test_consistency.py"),
)
INTERPRETERS = frozenset({"sh", "python", "python3"})

STUBBED = (
    "ansible-galaxy",
    "ansible-lint",
    "ansible-playbook",
    "bats",
    "python",
    "python3",
    "ruff",
    "sh",
    "shellcheck",
)
REAL = ("dirname", "grep", "ls", "mktemp", "rm", "sed", "tail", "tee", "xargs")

# How the runner starts a run block (GitHub Actions "jobs.<id>.steps[*].shell").
SHELLS: dict[Any, tuple[str, ...]] = {
    None: ("bash", "-e"),
    "bash": ("bash", "--noprofile", "--norc", "-eo", "pipefail"),
    "sh": ("sh", "-e"),
}
JOB_KEYS = frozenset({"name", "runs-on", "steps", "timeout-minutes", "permissions"})
RUN_STEP_KEYS = frozenset({"name", "id", "run", "shell"})
USES_STEP_KEYS = frozenset({"name", "id", "uses", "with", "if"})

FIELD = "\x1f"
RECORD = "\x1e"
# Records one invocation and fails only the one the fixture names.
STUB = """#!/bin/sh
name=${0##*/}
sep=$(printf '\\037')
joined=$name
for arg in "$@"; do
  joined="$joined$sep$arg"
done
printf '%s\\036' "$joined" >> "$PARITY_LOG" || exit 125
if [ "$joined" = "${PARITY_FAIL-}" ]; then
  exit 1
fi
exit 0
"""
TIMEOUT = 120

Command = tuple[str, ...]


class UniqueKeyLoader(yaml.SafeLoader):
    """Refuse ambiguous mappings instead of silently keeping the last value."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        self.flatten_mapping(node)
        keys: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate YAML key {key!r}", key_node.start_mark
                )
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def show(command: Command) -> str:
    return shlex.join(command)


def load_workflow(text: str, errors: list[str]) -> list[dict[str, Any]]:
    """Return the validate job's steps, or nothing when it cannot be modelled."""
    try:
        workflow = yaml.load(text, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        errors.append(f"{WORKFLOW} cannot be parsed: {exc}")
        return []
    if not isinstance(workflow, dict):
        errors.append(f"{WORKFLOW} root must be a mapping")
        return []

    # YAML 1.1 reads the bare key `on` as true.
    triggers = workflow.get("on", workflow.get(True))
    if not (
        isinstance(triggers, dict)
        and "push" in triggers
        and "pull_request" in triggers
        and triggers["push"] is None
        and triggers["pull_request"] is None
    ):
        errors.append("CI must run on every push and every pull request, unfiltered")
    for key in ("defaults", "env"):
        if key in workflow:
            errors.append(f"CI sets workflow-wide {key!r}, which this contract does not model")

    jobs = workflow.get("jobs")
    job = jobs.get(JOB) if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        errors.append(f"CI has no {JOB!r} job")
        return []
    for key in sorted(set(job) - JOB_KEYS, key=str):
        errors.append(f"the {JOB} job sets {key!r}, which could skip or soften its checks")

    steps = job.get("steps")
    if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
        errors.append(f"the {JOB} job steps must be a list of mappings")
        return []

    toolchain = []
    ids: set[str] = set()
    for number, step in enumerate(steps, start=1):
        label = f"{JOB} step {number} ({step.get('name', 'unnamed')!r})"
        if "id" in step:
            identity = step["id"]
            if not isinstance(identity, str) or not identity:
                errors.append(f"{label} id must be a nonempty string")
            elif identity in ids:
                errors.append(f"{label} has duplicate step id {identity!r}")
            else:
                ids.add(identity)
        if ("run" in step) == ("uses" in step):
            errors.append(f"{label} must have exactly one of run and uses")
            continue
        if "uses" in step:
            for key in sorted(set(step) - USES_STEP_KEYS, key=str):
                errors.append(f"{label} sets {key!r}")
            continue
        for key in sorted(set(step) - RUN_STEP_KEYS, key=str):
            errors.append(f"{label} sets {key!r}, which could skip or soften its commands")
        if not isinstance(step["run"], str):
            errors.append(f"{label} run block must be a string")
        elif "${{" in step["run"]:
            errors.append(f"{label} run block holds an expression this contract does not model")
        shell = step.get("shell")
        if (shell is not None and not isinstance(shell, str)) or shell not in SHELLS:
            errors.append(f"{label} uses shell {shell!r}, which this contract does not model")
        if step.get("id") == TOOLCHAIN:
            toolchain.append(number)
    if len(toolchain) != 1:
        errors.append(f"the {JOB} job must have exactly one run step with id {TOOLCHAIN!r}")
    return steps


def read_records(log: Path) -> list[Command]:
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    if text and not text.endswith(RECORD):
        raise ValueError(f"unterminated stub record in {log}")
    return [tuple(entry.split(FIELD)) for entry in text.split(RECORD)[:-1]]


def tool_checks(records: list[Command]) -> Counter[Command]:
    return Counter(
        record
        for record in records
        if record[0] in INTERPRETERS and len(record) > 1 and record[1].startswith("tools/")
    )


class Fixture:
    """A temporary checkout of the two entrypoints and a PATH of stubs."""

    def __init__(self, base: Path, verify_text: str, workflow_text: str) -> None:
        self.base = base
        self.checkout = base / "checkout"
        (self.checkout / WORKFLOW.parent).mkdir(parents=True)
        (self.checkout / WORKFLOW).write_text(workflow_text, encoding="utf-8")
        (self.checkout / VERIFY).write_text(verify_text, encoding="utf-8")
        (self.checkout / VERIFY).chmod(0o755)
        self.home = base / "home"
        self.home.mkdir()
        self.scripts = base / "scripts"
        self.scripts.mkdir()
        self.password = base / "become-password"
        self.password.write_text("unused\n", encoding="utf-8")

        stubs = base / "stubs"
        stubs.mkdir()
        for name in STUBBED:
            path = stubs / name
            path.write_text(STUB, encoding="utf-8")
            path.chmod(0o755)
        real = base / "real"
        real.mkdir()
        for name in REAL:
            found = shutil.which(name)
            if found is None:
                raise FileNotFoundError(f"{name} is not installed")
            (real / name).symlink_to(found)
        self.path = f"{stubs}{os.pathsep}{real}"
        self.interpreters = {}
        for name in ("bash", "sh"):
            found = shutil.which(name)
            if found is None:
                raise FileNotFoundError(f"{name} is not installed")
            self.interpreters[name] = found
        self.runs = 0

    def execute(self, argv: list[str], fail: Command | None, extra: dict[str, str]) -> tuple[int, list[Command]]:
        self.runs += 1
        log = self.base / f"run-{self.runs}.log"
        env = {
            "PATH": self.path,
            "HOME": str(self.home),
            "LC_ALL": "C",
            "PARITY_LOG": str(log),
            "PARITY_FAIL": FIELD.join(fail) if fail else "",
            **extra,
        }
        result = subprocess.run(
            argv,
            cwd=self.checkout,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT,
            check=False,
        )
        return result.returncode, read_records(log)

    def run_ci(self, steps: list[dict[str, Any]], fail: Command | None) -> tuple[str | None, list[Command]]:
        """Run the job's steps as the runner does; return the failed step and the calls."""
        failed: str | None = None
        records: list[Command] = []
        for number, step in enumerate(steps, start=1):
            # uses steps are the checkout, which the fixture stands in for,
            # and the uploads that run only after a failure.
            if "run" not in step or step.get("id") == TOOLCHAIN:
                continue
            if failed is not None:
                # No step here has an `if`, so each runs only while the job succeeds.
                continue
            shell, *flags = SHELLS[step.get("shell")]
            script = self.scripts / f"step-{self.runs + 1}-{number}.sh"
            script.write_text(step["run"], encoding="utf-8")
            code, calls = self.execute(
                [self.interpreters[shell], *flags, str(script)], fail, {}
            )
            records.extend(calls)
            if code != 0:
                failed = f"{number} ({step.get('name', 'unnamed')!r}) exited {code}"
        return failed, records

    def run_verify(self, fail: Command | None) -> tuple[int, list[Command]]:
        # A readable password file sends the render level straight to the
        # stubbed ansible-playbook: verify.sh never reaches sudo here.
        return self.execute(
            [self.interpreters["bash"], str(self.checkout / VERIFY)],
            fail,
            {"PRIVATESTACK_BECOME_PASSWORD_FILE": str(self.password)},
        )


def compare(where: str, ran: Counter[Command], errors: list[str]) -> None:
    for command in EXPECTED:
        if ran[command] == 0:
            errors.append(f"{where} did not run {show(command)}")
        elif ran[command] > 1:
            errors.append(f"{where} ran {show(command)} {ran[command]} times")
    for command in sorted(set(ran) - set(EXPECTED)):
        errors.append(f"{where} ran {show(command)}, which is not one of the six shell, palette and choices checks")


def collect_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    try:
        for relative in (WORKFLOW, VERIFY):
            path = root / relative
            if path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
                return [f"{relative}: entrypoint must be a regular, unredirected file"]
        workflow_text = (root / WORKFLOW).read_text(encoding="utf-8")
        verify_text = (root / VERIFY).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"cannot read an entrypoint: {exc}"]

    steps = load_workflow(workflow_text, errors)
    if errors:
        return errors

    with tempfile.TemporaryDirectory(prefix="hyperlab-ci-parity-") as tmp:
        try:
            fixture = Fixture(Path(tmp), verify_text, workflow_text)
            failed, ci_records = fixture.run_ci(steps, None)
            verify_code, verify_records = fixture.run_verify(None)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return [f"the fixture could not run: {exc}"]

        if failed is not None:
            errors.append(f"CI failed with every stub passing: step {failed}")
        if verify_code != 0:
            errors.append(f"verify.sh exited {verify_code} with every stub passing")
        ci_checks = tool_checks(ci_records)
        verify_checks = tool_checks(verify_records)
        compare("CI", ci_checks, errors)
        compare("verify.sh", verify_checks, errors)
        if ci_checks != verify_checks:
            only_ci = sorted(show(c) for c in set(ci_checks) - set(verify_checks))
            only_verify = sorted(show(c) for c in set(verify_checks) - set(ci_checks))
            errors.append(
                "CI and verify.sh run different tool checks: "
                f"only CI {only_ci}, only verify.sh {only_verify}"
            )

        for command in EXPECTED:
            try:
                failed, ci_records = fixture.run_ci(steps, command)
                verify_code, verify_records = fixture.run_verify(command)
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                return [*errors, f"the fixture could not run: {exc}"]
            if command not in ci_records:
                errors.append(f"CI did not reach {show(command)} when it was made to fail")
            elif failed is None:
                errors.append(f"CI succeeded while {show(command)} failed")
            if command not in verify_records:
                errors.append(f"verify.sh did not reach {show(command)} when it was made to fail")
            elif verify_code == 0:
                errors.append(f"verify.sh exited 0 while {show(command)} failed")
    return errors


def main() -> int:
    errors = collect_errors()
    if errors:
        print("CI VERIFY PARITY CONTRACT FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("ci verify parity contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
