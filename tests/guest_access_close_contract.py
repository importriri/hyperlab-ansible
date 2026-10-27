#!/usr/bin/env python3
"""A Machine's first provisioning ends by closing its access (milestone 10).

The last provisioning step, playbooks/guest-close-access.yml, must:

  1. allow the QEMU Guest Agent exactly the calls HyperLab and libvirt use
     (decided 2026-10-04) and never guest-exec or a file write, in the
     comma-separated allow-rpcs form qemu-ga reads, and restart the agent
     while become still needs no password;
  2. remove cloud-init's NOPASSWD rule only when the account has a usable
     password, after a visudo-validated rule lets the administrator group
     sudo with that password, as the last task that uses become, and then
     prove sudo asks for the password;
  3. prove from the host that guest-exec is disabled and that the SSH host
     key read through the agent still matches the pinned one;
  4. be the one source of the agent restriction a disposable Machine's seed
     writes on every boot (ADR 0018): the same file, from this allowlist.
"""

from __future__ import annotations

import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import guest_contract  # noqa: E402

ROLE = ROOT / "roles/guest_access_close"
EXPECTED_RPCS = [
    "guest-sync-delimited", "guest-sync", "guest-ping", "guest-info", "guest-get-host-name",
    "guest-network-get-interfaces", "guest-shutdown", "guest-file-open", "guest-file-read",
    "guest-file-close",
]
PLAYBOOK = Path("playbooks/guest-close-access.yml")
ROLE_TASKS = Path("roles/guest_access_close/tasks/main.yml")
EXEC_NAME = "Refuse unless guest-exec is disabled"
PIN_NAME = "Refuse a host key that differs from the pinned one"
SUDO_NAME = "Prove sudo now asks for the password"


class UniqueKeyLoader(yaml.SafeLoader):
    """Ambiguous YAML is not evidence of the condition Ansible would use."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        self.flatten_mapping(node)
        mapping = super().construct_mapping(node, deep=deep)
        keys: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate YAML key {key!r}", key_node.start_mark
                )
            keys.add(key)
        return mapping


@dataclass(frozen=True)
class ConditionCase:
    name: str
    variables: dict[str, Any]
    # None requires an explicit Ansible rejection, never a boolean success.
    failed: bool | None


def condition_cases() -> dict[str, tuple[ConditionCase, ...]]:
    """Expected outcomes are independent of the expressions under test."""
    disabled = "error: internal error: guest agent command 'guest-exec' has been disabled"
    exec_rows = (
        ("successful execution", 0, "", "", True),
        ("successful execution with disabled stderr", 0, disabled, "", True),
        ("disabled stderr", 1, disabled, "", False),
        ("mixed-case disabled stderr", 1, disabled.upper(), "", False),
        ("unavailable agent", 1, "error: Guest agent is not responding", "", True),
        ("timeout", 1, "error: guest agent command timed out", "", True),
        ("unrelated error", 1, "error: permission denied", "", True),
        ("empty stderr", 1, "", "", True),
        ("disabled only in stdout", 1, "", disabled, True),
    )
    # A synthetic public key, with the shape emitted by guest_host_key.py.
    key = "AAAAC3NzaC1lZDI1NTE5AAAAI" + "A" * 43
    host_key = f"192.0.2.10 ssh-ed25519 {key}\n"
    pinned = f"# Host 192.0.2.10 found: line 1\n192.0.2.10 ssh-ed25519 {key}\n"

    def pin_case(name: str, key_result: Any, pin_result: Any, failed: bool | None) -> ConditionCase:
        return ConditionCase(name, {
            "guest_close_host_key": key_result, "guest_close_pinned": pin_result,
        }, failed)

    return {
        "guest-exec": tuple(ConditionCase(name, {
            "guest_close_exec": {"rc": rc, "stderr": stderr, "stdout": stdout},
        }, failed) for name, rc, stderr, stdout, failed in exec_rows),
        "sudo": (
            ConditionCase("passwordless success", {"guest_access_close_sudo": {"rc": 0}}, True),
            ConditionCase("password required", {"guest_access_close_sudo": {
                "rc": 1, "stderr": "sudo: a password is required", "stdout": "",
            }}, False),
        ),
        "pinned key": (
            pin_case("matching key", {"stdout": host_key}, {"rc": 0, "stdout": pinned}, False),
            pin_case("mismatched key", {"stdout": host_key}, {
                "rc": 0, "stdout": "192.0.2.10 ssh-ed25519 another-key\n",
            }, True),
            pin_case("failed lookup with matching output", {"stdout": host_key}, {
                "rc": 1, "stdout": pinned,
            }, True),
            pin_case("missing host-key stdout", {}, {"rc": 0, "stdout": pinned}, None),
            pin_case("truncated host-key data", {"stdout": "192.0.2.10 ssh-ed25519"}, {
                "rc": 0, "stdout": pinned,
            }, None),
            pin_case("null host-key data", {"stdout": None}, {"rc": 0, "stdout": pinned}, None),
            pin_case("missing lookup stdout", {"stdout": host_key}, {"rc": 0}, None),
            pin_case("malformed lookup stdout", {"stdout": host_key}, {
                "rc": 0, "stdout": None,
            }, None),
            ConditionCase("missing registered result", {}, None),
        ),
    }


def named_task(tasks: Any, name: str) -> dict[str, Any]:
    require(isinstance(tasks, list) and all(isinstance(task, dict) for task in tasks),
            f"{name}: tasks must be a list of mappings")
    matches = [task for task in tasks if task.get("name") == name]
    require(len(matches) == 1, f"{name}: expected exactly one named task, got {len(matches)}")
    return matches[0]


def load_condition_input(root: Path, relative: Path, loader: DataLoader) -> Any:
    path = root / relative
    require(not any(part.is_symlink() for part in (path, *path.parents)),
            f"{relative}: condition input must not be redirected")
    mode = path.stat().st_mode
    require(stat.S_ISREG(mode) and bool(mode & 0o444),
            f"{relative}: condition input must be a readable regular file")
    # Validate uniqueness before Ansible's loader can accept a duplicate key.
    yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    # This is playbook source, trusted just as when Ansible loads a playbook.
    # Registered results below are data; they are never marked as templates.
    return loader.load_from_file(str(path), cache="none", trusted_as_template=True)


def collect_condition_errors(root: Path = ROOT) -> list[str]:
    """Evaluate only failed_when; no action plugin or host command is run."""
    loader = DataLoader()
    try:
        plays = load_condition_input(root, PLAYBOOK, loader)
        role_tasks = load_condition_input(root, ROLE_TASKS, loader)
        host_play = named_task(plays, "Prove the agent restriction from the host")
        block = named_task(role_tasks, "End passwordless sudo once the account has a password")
        tasks = {
            "guest-exec": (named_task(host_play.get("tasks"), EXEC_NAME), "guest_close_exec"),
            "sudo": (named_task(block.get("block"), SUDO_NAME), "guest_access_close_sudo"),
            "pinned key": (named_task(host_play.get("tasks"), PIN_NAME), "guest_close_pinned"),
        }
        guards: dict[str, list[str | bool]] = {}
        for label, (task, register) in tasks.items():
            require(task.get("register") == register, f"{label}: registered result changed")
            require("failed_when" in task, f"{label}: missing failed_when")
            guard = task["failed_when"]
            conditions = guard if isinstance(guard, list) else [guard]
            require(bool(conditions) and all(
                isinstance(item, bool) or isinstance(item, str) and bool(item.strip())
                for item in conditions
            ), f"{label}: malformed failed_when")
            guards[label] = conditions
    except (AssertionError, OSError, UnicodeError, yaml.YAMLError, AnsibleError) as exc:
        return [f"condition input rejected: {exc}"]

    errors = []
    for label, cases in condition_cases().items():
        for case in cases:
            templar = Templar(loader=loader, variables=case.variables)
            try:
                # Ansible lists of conditions are conjunctions. Every expression
                # itself goes through its native evaluator, including filters.
                failed = all(templar.evaluate_conditional(item) for item in guards[label])
            except AnsibleError as exc:
                if case.failed is not None:
                    errors.append(f"{label} / {case.name}: Ansible rejected a valid control: {exc}")
                continue
            if case.failed is None:
                errors.append(f"{label} / {case.name}: expected Ansible rejection, got {failed}")
            elif failed is not case.failed:
                expected = "refusal" if case.failed else "success"
                actual = "refusal" if failed else "success"
                errors.append(f"{label} / {case.name}: expected {expected}, got {actual}")
    return errors


def check_condition_mutations(root: Path, selected: str | None = None) -> None:
    """Discovery must catch weakened YAML, using the same evaluator as above."""
    mutations = (
        ("or to and", "guest-exec", " or ", " and ", (
            "guest-exec / successful execution with disabled stderr: expected refusal, got success",
            "guest-exec / unavailable agent: expected refusal, got success",
        )),
        ("constant false", "guest-exec", None, False, (
            "guest-exec / successful execution: expected refusal, got success",
            "guest-exec / unavailable agent: expected refusal, got success",
        )),
        ("omitted stderr", "guest-exec", " or ", "first", (
            "guest-exec / unavailable agent: expected refusal, got success",
        )),
        ("constant true", "guest-exec", None, True, (
            "guest-exec / disabled stderr: expected success, got refusal",
        )),
        ("reversed sudo", "sudo", " == ", " != ", (
            "sudo / passwordless success: expected refusal, got success",
            "sudo / password required: expected success, got refusal",
        )),
        ("omitted lookup rc", "pinned key", " or ", "last", (
            "pinned key / failed lookup with matching output: expected refusal, got success",
        )),
    )
    require(selected is None or selected in {item[0] for item in mutations},
            f"unknown condition mutation {selected}")
    sources = {relative: (root / relative).read_bytes() for relative in (PLAYBOOK, ROLE_TASKS)}
    require(not collect_condition_errors(root), "condition mutation baseline failed")
    with tempfile.TemporaryDirectory(prefix="hyperlab-access-conditions-") as tmp:
        copy = Path(tmp)
        for relative in sources:
            target = copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
        for name, group, old, new, expected in mutations:
            if selected is not None and name != selected:
                continue
            require(not collect_condition_errors(copy), f"{name}: clean control failed")
            relative = ROLE_TASKS if group == "sudo" else PLAYBOOK
            path = copy / relative
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if group == "sudo":
                block = named_task(data, "End passwordless sudo once the account has a password")
                task = named_task(block["block"], SUDO_NAME)
            else:
                play = named_task(data, "Prove the agent restriction from the host")
                task = named_task(play["tasks"], EXEC_NAME if group == "guest-exec" else PIN_NAME)
            expression = task["failed_when"]
            if old is None:
                task["failed_when"] = new
            else:
                require(isinstance(expression, str) and expression.count(old) == 1,
                        f"{name}: mutation target is no longer unique")
                if new in ("first", "last"):
                    task["failed_when"] = expression.split(old)[0 if new == "first" else 1]
                else:
                    task["failed_when"] = expression.replace(old, new, 1)
            try:
                path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
                errors = collect_condition_errors(copy)
                for diagnostic in expected:
                    require(diagnostic in errors,
                            f"{name}: mutation did not fail at {diagnostic!r}; got {errors}")
            finally:
                path.write_bytes(sources[relative])
            require(not collect_condition_errors(copy), f"{name}: restored control failed")
    require(all((root / relative).read_bytes() == source for relative, source in sources.items()),
            "condition mutation changed production input bytes")
    require(not collect_condition_errors(root), "condition mutation final control failed")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    errors = collect_condition_errors(ROOT)
    require(not errors, "\n".join(errors))
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    rpcs = defaults["guest_access_close_agent_rpcs"]
    require(rpcs == EXPECTED_RPCS, f"the agent allowlist changed: {rpcs}")
    for forbidden in ("guest-exec", "guest-exec-status", "guest-file-write", "guest-set-user-password",
                      "guest-ssh-add-authorized-keys"):
        require(forbidden not in rpcs, f"{forbidden} is allowed")
    # Every call HyperLab makes through the agent is on the list.
    host_key = (ROOT / "tools/guest_host_key.py").read_text()
    for call in ("guest-file-open", "guest-file-read", "guest-file-close"):
        require(call in host_key and call in rpcs, f"{call} is used but not allowed")
    address = (ROOT / "tools/guest_agent_address.py").read_text()
    require('"--source",\n        "agent"' in address and "guest-network-get-interfaces" in rpcs,
            "the agent address lookup would be refused")

    tasks_text = (ROLE / "tasks/main.yml").read_text()
    require("allow-rpcs={{ guest_access_close_agent_rpcs | join(',') }}" in tasks_text
            and "[general]" in tasks_text, "the agent configuration is not in the form qemu-ga reads")
    tasks = yaml.safe_load(tasks_text)
    names = [task["name"] for task in tasks]
    restart = names.index("Restart the agent on its restricted configuration")
    require(tasks[restart].get("ansible.builtin.meta") == "flush_handlers",
            "the agent restart waits for the end of the play, after sudo needs a password")
    block_task = next(task for task in tasks if task["name"] == "End passwordless sudo once the account has a password")
    require(names.index(block_task["name"]) > restart, "sudo closes before the agent restarts")
    require(block_task["when"] == "guest_access_close_has_password",
            "NOPASSWD is removed even when the account has no password")
    block = block_task["block"]
    admin = next(i for i, task in enumerate(block) if task["name"] == "Let the administrator group sudo with its password")
    remove = next(i for i, task in enumerate(block) if task["name"] == "Remove cloud-init's passwordless sudo rule")
    require(block[admin]["ansible.builtin.copy"].get("validate") == "visudo -cf %s" and admin < remove,
            "the password rule is not validated before NOPASSWD goes")
    require(all(task.get("become") is False for task in block[remove + 1:])
            and all(task.get("become") is False for task in tasks[names.index(block_task["name"]) + 1:]),
            "a task after the NOPASSWD removal still needs passwordless become")
    proof = block[remove + 1]
    require(proof["ansible.builtin.command"]["argv"] == ["sudo", "-n", "true"]
            and proof["name"] == SUDO_NAME,
            "nothing proves sudo now asks for the password")

    playbook = yaml.safe_load((ROOT / "playbooks/guest-close-access.yml").read_text())
    host_tasks = playbook[1]["tasks"]
    exec_task = next(task for task in host_tasks if task["name"] == "Refuse unless guest-exec is disabled")
    require("guest-exec" in " ".join(exec_task["ansible.builtin.command"]["argv"]),
            "guest-exec is not proven disabled")
    require(any("guest_host_key.py" in " ".join(task.get("ansible.builtin.command", {}).get("argv", []))
                for task in host_tasks), "the host key is not read again after the restriction")
    require(any("ssh-keygen" in task.get("ansible.builtin.command", {}).get("argv", [""])[0]
                for task in host_tasks), "the re-read key is not compared with the pinned one")
    check_condition_mutations(ROOT)


    # ADR 0018: a disposable boot writes this role's file from this list.
    rendered_rpcs, content = guest_contract.close_role_agent_conf()
    require(rendered_rpcs == rpcs, "the close role's list was read differently")
    seed = guest_contract.load_unique(guest_contract.render_seeds({"seed": guest_contract.seed_case({})})["seed"])
    files, restarts = guest_contract.agent_entries(seed)
    require([item["content"] for item in files] == [content] and restarts == [guest_contract.AGENT_RESTART],
            "a disposable seed does not restore this role's agent restriction")
    print("Guest access close contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
