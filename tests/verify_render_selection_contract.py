#!/usr/bin/env python3
"""verify.sh runs every render invariant it can and names the one it cannot.

tests/render.yml has one task that needs root, the nft -c judge, tagged
"privileged". Without any sudo credential, verify.sh must still run the rest
of the suite with --skip-tags privileged, report that judge as not run and
end nonzero and incomplete, never ALL GREEN. A supplied password file or
passwordless sudo must run the complete suite; an unreadable supplied file
must refuse instead of falling back to the partial run.

This contract runs the shipped verify.sh in temporary checkouts where every
tool it calls, sudo included, is a recording stub, with stdin redirected and
stdout either a pipe or a terminal (verify.sh invokes the render suite from
two places, one for each). It compares the executed argv, the number of
calls, the exit status and the verdict printed at the end. No real sudo,
password or Ansible run is involved.
"""

from __future__ import annotations

import os
import pty
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = Path("verify.sh")

# The render invocation, written out here rather than read from verify.sh,
# so that an edit to verify.sh cannot change what is required.
RENDER = ("-i", "inventory.ini", "tests/render.yml")
EXTRA_VARS = (
    "--extra-vars",
    '{"hardware_profiles":{"nitro-3060":{"vfio_ids":["10de:2520","10de:228e"]}}}',
)
SKIP_PRIVILEGED = ("--skip-tags", "privileged")
SUDO_PROBE = ("sudo", "-n", "true")

GREEN = "ALL GREEN - ready to commit."
FAILED = "VERIFICATION FAILED - read above. No commit until this is green."
INCOMPLETE = (
    "VERIFICATION INCOMPLETE - every check that ran passed, "
    "but the privileged nft -c judge did not run."
)
VERDICTS = (GREEN, FAILED, INCOMPLETE)
JUDGE_NOT_RUN = "   NOT RUN - the privileged nft -c judge of tests/render.yml (no sudo credentials)"
LEVEL_2B = "== level 2b - render / invariant tests"
UNREADABLE = "Configured become password file is not readable."

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
    "sudo",
)
REAL = ("dirname", "grep", "ls", "mktemp", "rm", "sed", "tail", "xargs")

FIELD = "\x1f"
RECORD = "\x1e"
# Records one invocation. sudo answers with STUB_SUDO_STATUS (refusing by
# default); the render suite fails when STUB_RENDER_FAIL is set; the tool
# named by STUB_FAIL fails on every call.
STUB = """#!/bin/sh
name=${0##*/}
sep=$(printf '\\037')
joined=$name
for arg in "$@"; do
  joined="$joined$sep$arg"
done
printf '%s\\036' "$joined" >> "$RENDER_LOG" || exit 125
if [ "$name" = sudo ]; then
  exit "${STUB_SUDO_STATUS:-1}"
fi
if [ "$name" = "${STUB_FAIL-}" ]; then
  exit 1
fi
if [ "$name" = ansible-playbook ] && [ -n "${STUB_RENDER_FAIL-}" ]; then
  for arg in "$@"; do
    if [ "$arg" = tests/render.yml ]; then
      exit 1
    fi
  done
fi
exit 0
"""
TIMEOUT = 120

Command = tuple[str, ...]


@dataclass(frozen=True)
class Case:
    name: str
    # "file": a readable PRIVATESTACK_BECOME_PASSWORD_FILE; "missing" and
    # "unreadable": a configured file that cannot be read; "passwordless":
    # sudo -n true succeeds; "none": no file and sudo -n true refuses.
    credential: str
    render_fails: bool = False
    other_fails: str = ""


CASES = (
    Case("partial success", "none"),
    Case("partial render failure", "none", render_fails=True),
    Case("partial run with a lint failure", "none", other_fails="ruff"),
    Case("full success with a supplied file", "file"),
    Case("full failure with a supplied file", "file", render_fails=True),
    Case("passwordless full success", "passwordless"),
    Case("passwordless full failure", "passwordless", render_fails=True),
    Case("supplied file missing", "missing"),
    Case("supplied file unreadable", "unreadable"),
)


def show(command: Command) -> str:
    return " ".join(command)


def read_records(log: Path) -> list[Command]:
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    if text and not text.endswith(RECORD):
        raise ValueError(f"unterminated stub record in {log}")
    return [tuple(entry.split(FIELD)) for entry in text.split(RECORD)[:-1]]


def run_on_terminal(argv: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    """Run with stdout and stderr on a pseudo-terminal, stdin still redirected."""
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
        )
    finally:
        os.close(slave)
    chunks: list[bytes] = []

    def drain() -> None:
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:
                # EIO once every writer has closed the terminal.
                return
            if not data:
                return
            chunks.append(data)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        reader.join(TIMEOUT)
        os.close(master)
    return code, b"".join(chunks).decode("utf-8", "replace").replace("\r\n", "\n")


class Fixture:
    """A temporary checkout holding only verify.sh, and a PATH of stubs."""

    def __init__(self, base: Path, verify_text: str) -> None:
        self.base = base
        self.checkout = base / "checkout"
        self.checkout.mkdir()
        (self.checkout / VERIFY).write_text(verify_text, encoding="utf-8")
        (self.checkout / VERIFY).chmod(0o755)
        self.home = base / "home"
        self.home.mkdir()
        self.password = base / "become-password"
        self.password.write_text("unused\n", encoding="utf-8")
        self.missing = base / "absent-become-password"
        self.unreadable = base / "unreadable-become-password"
        self.unreadable.write_text("unused\n", encoding="utf-8")
        self.unreadable.chmod(0)

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
        bash = shutil.which("bash")
        if bash is None:
            raise FileNotFoundError("bash is not installed")
        self.bash = bash
        self.runs = 0

    def password_file(self, credential: str) -> str | None:
        return {
            "file": str(self.password),
            "missing": str(self.missing),
            "unreadable": str(self.unreadable),
        }.get(credential)

    def execute(self, case: Case, terminal: bool) -> tuple[int, str, list[Command]]:
        self.runs += 1
        log = self.base / f"run-{self.runs}.log"
        env = {
            "PATH": self.path,
            "HOME": str(self.home),
            "LC_ALL": "C",
            "RENDER_LOG": str(log),
            "STUB_SUDO_STATUS": "0" if case.credential == "passwordless" else "1",
            "STUB_FAIL": case.other_fails,
        }
        if case.render_fails:
            env["STUB_RENDER_FAIL"] = "1"
        password = self.password_file(case.credential)
        if password is not None:
            env["PRIVATESTACK_BECOME_PASSWORD_FILE"] = password
        argv = [self.bash, str(self.checkout / VERIFY)]
        if terminal:
            code, output = run_on_terminal(argv, self.checkout, env)
        else:
            result = subprocess.run(
                argv,
                cwd=self.checkout,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT,
                check=False,
            )
            code, output = result.returncode, result.stdout.decode("utf-8", "replace")
        return code, output, read_records(log)


def expected_render(fixture: Fixture, case: Case) -> list[Command]:
    if case.credential == "none":
        return [("ansible-playbook", *RENDER, *SKIP_PRIVILEGED, *EXTRA_VARS)]
    if case.credential == "file":
        become = ("--become-password-file", str(fixture.password))
        return [("ansible-playbook", *become, *RENDER, *EXTRA_VARS)]
    if case.credential == "passwordless":
        return [("ansible-playbook", *RENDER, *EXTRA_VARS)]
    return []


def level_2b(lines: list[str]) -> list[str] | None:
    if lines.count(LEVEL_2B) != 1:
        return None
    start = lines.index(LEVEL_2B) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("== ") or lines[i] in VERDICTS),
        len(lines),
    )
    return lines[start:end]


def check_case(fixture: Fixture, case: Case, terminal: bool, errors: list[str]) -> None:
    where = f"{case.name} ({'terminal' if terminal else 'pipe'})"
    code, output, records = fixture.execute(case, terminal)
    lines = output.splitlines()

    render = [r for r in records if r[0] == "ansible-playbook" and "tests/render.yml" in r]
    wanted = expected_render(fixture, case)
    if render != wanted:
        errors.append(
            f"{where}: render suite ran {[show(r) for r in render]}, "
            f"expected {[show(r) for r in wanted]}"
        )
    sudo = [r for r in records if r[0] == "sudo"]
    wanted_sudo = [SUDO_PROBE] if case.credential in ("none", "passwordless") else []
    if sudo != wanted_sudo:
        errors.append(
            f"{where}: sudo ran {[show(r) for r in sudo]}, expected {[show(r) for r in wanted_sudo]}"
        )
    prompted = [r for r in records if "-K" in r or "--ask-become-pass" in r]
    if prompted:
        errors.append(f"{where}: asked for a become password: {[show(r) for r in prompted]}")
    if case.other_fails and not any(r[0] == case.other_fails for r in records):
        errors.append(f"{where}: never ran {case.other_fails}, the tool made to fail")

    complete = case.credential in ("file", "passwordless")
    passed = complete and not case.render_fails and not case.other_fails
    wanted_code = 0 if passed else 1
    if code != wanted_code:
        errors.append(f"{where}: verify.sh exited {code}, expected {wanted_code}")

    if passed:
        wanted_verdict = GREEN
    elif case.credential == "none" and not case.render_fails and not case.other_fails:
        wanted_verdict = INCOMPLETE
    else:
        wanted_verdict = FAILED
    verdicts = [line for line in lines if line in VERDICTS]
    if verdicts != [wanted_verdict]:
        errors.append(f"{where}: verdict {verdicts}, expected [{wanted_verdict!r}]")

    section = level_2b(lines)
    if section is None:
        errors.append(f"{where}: level 2b is not reported exactly once")
        return
    judge_lines = section.count(JUDGE_NOT_RUN)
    wanted_judge = 1 if case.credential == "none" else 0
    if judge_lines != wanted_judge:
        errors.append(
            f"{where}: level 2b reports the nft -c judge as not run {judge_lines} times, "
            f"expected {wanted_judge}"
        )
    if case.credential in ("missing", "unreadable"):
        if UNREADABLE not in section:
            errors.append(f"{where}: level 2b does not refuse the unreadable password file")
        return
    render_status = [line for line in section if line in ("   OK", "   FAIL") or line.startswith("   FAIL ")]
    wanted_status = "   FAIL" if case.render_fails else "   OK"
    if [line.split(" -", 1)[0] for line in render_status] != [wanted_status]:
        errors.append(f"{where}: level 2b render status {render_status}, expected {wanted_status!r}")


def collect_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    path = root / VERIFY
    try:
        if path.resolve() != path or not stat.S_ISREG(path.lstat().st_mode):
            return [f"{VERIFY}: entrypoint must be a regular, unredirected file"]
        verify_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"cannot read {VERIFY}: {exc}"]

    with tempfile.TemporaryDirectory(prefix="hyperlab-render-selection-") as tmp:
        try:
            fixture = Fixture(Path(tmp), verify_text)
            for case in CASES:
                # Root reads a mode 0 file anyway; the missing file covers it.
                if case.credential == "unreadable" and os.geteuid() == 0:
                    continue
                for terminal in (False, True):
                    check_case(fixture, case, terminal, errors)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return [*errors, f"the fixture could not run: {exc}"]
    return errors


def main() -> int:
    errors = collect_errors()
    if errors:
        print("VERIFY RENDER SELECTION CONTRACT FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("verify render selection contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
