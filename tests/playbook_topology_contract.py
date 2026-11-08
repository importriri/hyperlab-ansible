#!/usr/bin/env python3
"""Structural contracts for the operator-facing playbook hierarchy.

The v1 host target, playbooks/v1-host.yml, is followed through its real
imports: the closure is lab.yml's, then the Hyprland component, then the
VFIO sleep guard, each once. Its Hyprland import arms the existing
managed-session lifecycle opt-in, and the installed Ansible engine
evaluates the role tasks with the play's effective variables to prove the
managed session catalog, both session targets and the Quickshell coupling
are staged. A single exact reconciliation play follows final deployment. No task runs and no host is contacted.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
V1_HOST = "playbooks/v1-host.yml"
LIFECYCLE = "host_desktop_hyprland_session_lifecycle_enabled"
# Keys a play in the followed closure may carry. A play with tasks,
# pre_tasks, post_tasks or handlers could hide a role from this closure.
PLAY_KEYS = {"name", "hosts", "become", "gather_facts", "roles", "vars"}
IMPORT_KEYS = {"name", "import_playbook", "vars"}

# One explicit post-deployment boundary; all other inline tasks remain refused.
RESIDENT_REFRESH_PLAY = {
    "name": "Reconcile the resident shell after all desktop deployment",
    "hosts": "hypervisor", "become": True, "gather_facts": False,
    "tasks": [{
        "name": "Refresh the running HyperLab shell", "tags": ["hyperlab_provenance"],
        "become": True, "become_user": "{{ admin_user }}",
        "ansible.builtin.script": {
            "cmd": "{{ playbook_dir }}/../roles/host_desktop_common/handlers/refresh.py quickshell",
            "executable": "/usr/bin/python"},
        "register": "host_desktop_common_final_resident_refresh",
        "changed_when": "(host_desktop_common_final_resident_refresh.stdout | from_json).changed",
        "when": "not ansible_check_mode"}],
}


class UniqueKeyLoader(yaml.SafeLoader):
    """A duplicated key would shadow an import or an opt-in silently."""

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


class ImportRefused(AssertionError):
    """The playbook closure cannot be established from its source."""


@dataclass
class Closure:
    files: list[str] = field(default_factory=list)
    # (role name, role entry vars, import vars in force, defining file)
    roles: list[tuple[str, dict[str, Any], dict[str, Any], str]] = field(default_factory=list)


def load_yaml(path: str) -> Any:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def playbook_closure(root: Path, entry: str) -> Closure:
    """Follow import_playbook from ``entry``; refuse anything ambiguous.

    Imports are plain relative names inside the entry's directory. A
    missing, escaping, absolute, templated, symlinked, repeated or cyclic
    import is a refusal, as is a play the closure could not see into.
    """
    base = (root / entry).parent.resolve(strict=True)
    closure = Closure()

    def resolve(directory: Path, raw: Any, source: str) -> Path:
        if not isinstance(raw, str) or not raw or "{{" in raw or "{%" in raw:
            raise ImportRefused(f"{source}: import is not a plain file name: {raw!r}")
        if os.path.isabs(raw):
            raise ImportRefused(f"{source}: absolute import {raw!r}")
        lexical = Path(os.path.normpath(directory / raw))
        if not lexical.is_relative_to(base):
            raise ImportRefused(f"{source}: import {raw!r} escapes {base.name}/")
        if not lexical.exists() and not lexical.is_symlink():
            raise ImportRefused(f"{source}: import {raw!r} does not exist")
        try:
            real = lexical.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ImportRefused(f"{source}: import {raw!r} cannot be resolved: {exc}") from exc
        if real != lexical:
            raise ImportRefused(f"{source}: import {raw!r} is redirected by a symlink")
        if not lexical.is_file():
            raise ImportRefused(f"{source}: import {raw!r} is not a regular file")
        return lexical

    def visit(path: Path, inherited: dict[str, Any], stack: tuple[Path, ...]) -> None:
        label = path.relative_to(base).as_posix()
        if path in stack:
            raise ImportRefused(f"{label}: cyclic import")
        if label in closure.files:
            raise ImportRefused(f"{label}: imported twice")
        closure.files.append(label)
        try:
            plays = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ImportRefused(f"{label}: unreadable playbook: {exc}") from exc
        if not isinstance(plays, list) or not plays:
            raise ImportRefused(f"{label}: a playbook is a non-empty list of plays")
        for play in plays:
            if not isinstance(play, dict):
                raise ImportRefused(f"{label}: a play is a mapping")
            local = play.get("vars", {})
            if not isinstance(local, dict):
                raise ImportRefused(f"{label}: play vars are not a mapping")
            scope = {**inherited, **local}
            if "import_playbook" in play:
                if set(play) - IMPORT_KEYS:
                    raise ImportRefused(f"{label}: import carries {sorted(set(play) - IMPORT_KEYS)}")
                child = resolve(path.parent, play["import_playbook"], label)
                visit(child, scope, (*stack, path))
                continue
            if label == "v1-host.yml" and play == RESIDENT_REFRESH_PLAY:
                continue
            if set(play) - PLAY_KEYS:
                raise ImportRefused(f"{label}: play carries {sorted(set(play) - PLAY_KEYS)}")
            entries = play.get("roles")
            if not isinstance(entries, list) or not entries:
                raise ImportRefused(f"{label}: play has no role list")
            for entry_value in entries:
                name = role_name(entry_value)
                entry_vars = entry_value.get("vars", {}) if isinstance(entry_value, dict) else {}
                closure.roles.append((name, entry_vars, scope, label))

    entry_path = root / entry
    if entry_path.is_symlink() or not entry_path.is_file():
        raise ImportRefused(f"{entry}: entrypoint is not a regular file")
    visit(base / entry_path.name, {}, ())
    return closure


def role_name(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("role"))
    raise AssertionError(f"unexpected role entry: {entry!r}")


def test_foundation_is_the_complete_headless_host_target() -> None:
    plays = load_yaml("playbooks/foundation.yml")
    assert len(plays) == 1
    play = plays[0]
    assert play["hosts"] == "hypervisor"
    roles = [role_name(entry) for entry in play["roles"]]
    assert roles == [
        "base",
        "hardware_probe",
        "kvm_host",
        "vfio_boot",
        "network_domains",
        "lab_isolation",
        "gpu_handoff",
        "brick_guard",
        "bootstrap_storage",
        "brick_guard",
        "image_store",
    ]
    assert "host_desktop_sway" not in roles and "looking_glass" not in roles
    assert "guest" not in roles and "image_factory" not in roles


def test_lab_adds_only_the_interactive_host_layer() -> None:
    plays = load_yaml("playbooks/lab.yml")
    assert plays[0]["name"] == "Assemble the headless foundation first"
    assert plays[0]["import_playbook"] == "foundation.yml"
    assert plays[1]["hosts"] == "hypervisor"
    role_entries = plays[1]["roles"]
    roles = [role_name(entry) for entry in role_entries]

    assert roles == [
        "host_desktop_common",
        "brick_guard",
        "host_desktop_sway",
        "brick_guard",
        "looking_glass",
    ]

    assert (
        role_entries[1]["role"] == "brick_guard"
        and role_entries[1]["vars"]["brick_guard_brick"]
        == "host_desktop_sway"
    )

    assert (
        role_entries[3]["role"] == "brick_guard"
        and role_entries[3]["vars"]["brick_guard_brick"]
        == "looking_glass"
    )

    assert (
        roles.index("host_desktop_common")
        < roles.index("host_desktop_sway")
        < roles.index("looking_glass")
    )
    text = (ROOT / "playbooks/lab.yml").read_text(encoding="utf-8")
    assert "guest" not in text and "image_factory" not in text


def test_targeted_playbooks_remain_available() -> None:
    common = load_yaml("playbooks/host-desktop-common.yml")[0]
    host_desktop = load_yaml("playbooks/host-desktop-sway.yml")[0]
    looking_glass = load_yaml("playbooks/looking-glass.yml")[0]

    assert common["hosts"] == "hypervisor"
    assert common["roles"] == ["host_desktop_common"]

    assert host_desktop["hosts"] == "hypervisor"
    host_entries = host_desktop["roles"]
    host_roles = [role_name(entry) for entry in host_entries]

    assert host_roles == [
        "host_desktop_common",
        "brick_guard",
        "host_desktop_sway",
    ]

    assert (
        host_entries[1]["role"] == "brick_guard"
        and host_entries[1]["vars"]["brick_guard_brick"]
        == "host_desktop_sway"
    )

    assert looking_glass["hosts"] == "hypervisor"
    assert [role_name(entry) for entry in looking_glass["roles"]] == [
        "brick_guard",
        "looking_glass",
    ]


def test_operator_docs_match_the_playbook_topology() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    adr = (ROOT / "docs/adr/0014-cockpit-surface.md").read_text(encoding="utf-8")
    desktop_defaults = (ROOT / "roles/host_desktop_sway/defaults/main.yml").read_text(encoding="utf-8")
    assert "`playbooks/lab.yml` imports the complete foundation" in readme
    assert "`host-desktop-sway.yml` and `looking-glass.yml` playbooks remain available for focused" in readme
    assert "which `lab.yml` mounts before `looking_glass`" in adr
    assert "foundation.yml keeps a recovery host blind (TTY)" in desktop_defaults
    stale_claims = (
        "lab.yml` never mounts",
        "never by lab.yml",
        "never pulled in by the base lab playbook",
    )
    current_contract = "\n".join((readme, adr, desktop_defaults))
    assert not any(claim in current_contract for claim in stale_claims)


WRITE_ACTIONS = {"copy", "file", "lineinfile", "template"}
# Starting, restarting or running anything during apply is outside the
# Hyprland component: it stages files and asserts, it never launches.
LAUNCH_ACTIONS = {
    "command", "shell", "raw", "script", "service", "systemd", "systemd_service", "reboot",
}
INACTIVE_ASSERT = "Keep host Hyprland configuration side-by-side and inactive"
BOUNDARY_ASSERT = "Validate the optional Host Hyprland session lifecycle boundary"
LY_KEYS = {
    "custom_sessions": "/etc/ly/hyperlab-sessions",
    "waylandsessions": "null",
    "xsessions": "null",
    "xinitrc": "null",
    "shell": "false",
}
SESSIONS = ("hyperlab-hyprland.desktop", "hyperlab-sway.desktop")
USER_UNITS = "/etc/systemd/user"
WANTS = f"{USER_UNITS}/hyperlab-hyprland-session.target.wants"


@dataclass(frozen=True)
class Staged:
    role: str
    action: str
    dest: str
    src: str | None
    state: str | None
    line: str | None


@dataclass
class Evaluation:
    staged: list[Staged] = field(default_factory=list)
    hyprland_actions: set[str] = field(default_factory=set)
    # assert task name -> [(condition, value)]
    asserts: dict[str, list[tuple[str, bool]]] = field(default_factory=dict)
    lifecycle: list[Any] = field(default_factory=list)


_ENGINE_READY = False


def evaluate_playbook(root: Path, entry: str) -> Evaluation:
    """Evaluate host_desktop_hyprland and host_sleep_guard task inputs.

    The installed Ansible engine loads the playbook with its imports, role
    defaults, inventory and group_vars, then templates the ``when``, loop
    and arguments of every file-writing task with the variables Ansible
    gives that task. Two runtime results are fixed explicitly: a real apply
    (``ansible_check_mode`` false) and no persisted theme, so the palette
    is the reviewed fallback. Nothing is executed.
    """
    global _ENGINE_READY
    from ansible.inventory.manager import InventoryManager
    from ansible.parsing.dataloader import DataLoader
    from ansible.playbook import Playbook
    from ansible.playbook.block import Block
    from ansible.plugins.loader import init_plugin_loader
    from ansible.template import Templar
    from ansible.vars.manager import VariableManager

    if not _ENGINE_READY:
        init_plugin_loader()
        _ENGINE_READY = True
    loader = DataLoader()
    loader.set_basedir(str(root))
    inventory = InventoryManager(loader=loader, sources=[str(root / "inventory.ini")])
    manager = VariableManager(loader=loader, inventory=inventory)
    host = inventory.get_host("localhost")
    assert host is not None and "hypervisor" in [g.name for g in host.get_groups()]
    playbook = Playbook.load(str(root / entry), variable_manager=manager, loader=loader)

    def tasks(blocks: list[Any]) -> Iterator[Any]:
        for block in blocks:
            for item in block.block:
                if isinstance(item, Block):
                    yield from tasks([item])
                else:
                    yield item

    result = Evaluation()
    for play in playbook.get_plays():
        for task in tasks(play.compile()):
            role = task._role.get_name() if task._role is not None else None
            if role not in ("host_desktop_hyprland", "host_sleep_guard"):
                continue
            action = task.action.rsplit(".", 1)[-1]
            if role == "host_desktop_hyprland":
                result.hyprland_actions.add(action)
            variables = dict(manager.get_vars(play=play, host=host, task=task))
            variables["ansible_check_mode"] = False
            if role == "host_desktop_hyprland":
                result.lifecycle.append(variables[LIFECYCLE])
                variables["host_desktop_hyprland_active_theme"] = variables[
                    "host_desktop_hyprland_palette_fallback"
                ]
            templar = Templar(loader=loader, variables=variables)
            runs = all(templar.evaluate_conditional(condition) for condition in task.when)
            name = task.get_name().split(" : ", 1)[-1]
            if action == "assert" and name in (INACTIVE_ASSERT, BOUNDARY_ASSERT) and runs:
                that = task.args["that"]
                result.asserts[name] = [
                    (condition, bool(templar.evaluate_conditional(condition)))
                    for condition in (that if isinstance(that, list) else [that])
                ]
            if action not in WRITE_ACTIONS or not runs:
                continue
            items = templar.template(task.loop) if task.loop else [None]
            for item in items:
                args = Templar(loader=loader, variables={**variables, "item": item}).template(task.args)
                result.staged.append(
                    Staged(
                        role=role,
                        action=action,
                        dest=str(args.get("dest") or args.get("path")),
                        src=args.get("src"),
                        state=args.get("state"),
                        line=args.get("line"),
                    )
                )
    return result


def managed_lifecycle_gaps(evaluation: Evaluation) -> list[str]:
    """Why the evaluated target does not stage the managed lifecycle."""
    staged = evaluation.staged
    hypr = [item for item in staged if item.role == "host_desktop_hyprland"]
    gaps: list[str] = []

    def has(action: str, dest: str, **fields: Any) -> bool:
        return any(
            item.action == action
            and item.dest == dest
            and all(getattr(item, key) == value for key, value in fields.items())
            for item in hypr
        )

    if not evaluation.lifecycle or not all(value is True for value in evaluation.lifecycle):
        gaps.append(f"lifecycle opt-in is not a YAML true for every task: {evaluation.lifecycle!r}")
    if not has("file", "/etc/ly/hyperlab-sessions", state="directory"):
        gaps.append("managed Ly session catalog directory is not staged")
    for session in SESSIONS:
        if not has("copy", f"/etc/ly/hyperlab-sessions/{session}", src=session):
            gaps.append(f"managed catalog does not receive {session}")
    ly_lines = {
        item.line.split(" = ", 1)[0]: item.line.split(" = ", 1)[1]
        for item in hypr
        if item.action == "lineinfile" and item.dest == "/etc/ly/config.ini" and item.line
    }
    if ly_lines != LY_KEYS:
        gaps.append(f"Ly discovery is not restricted to the managed catalog: {ly_lines!r}")
    for target in ("hyperlab-hyprland-session.target", "hyperlab-sway-session.target"):
        if not has("copy", f"{USER_UNITS}/{target}", src=target):
            gaps.append(f"session target {target} is not staged")
    if not has("copy", f"{USER_UNITS}/hyperlab-quickshell.service", src="hyperlab-quickshell.service"):
        gaps.append("the Quickshell user unit is not installed")
    if not has("file", WANTS, state="directory"):
        gaps.append("the managed Hyprland target has no wants directory")
    if not has(
        "file",
        f"{WANTS}/hyperlab-quickshell.service",
        src=f"{USER_UNITS}/hyperlab-quickshell.service",
        state="link",
    ):
        gaps.append("Quickshell is not coupled to the managed Hyprland target")
    if not has("copy", "/usr/local/bin/privatestack-session-lifecycle"):
        gaps.append("the session controller is not staged")
    for name in (INACTIVE_ASSERT, BOUNDARY_ASSERT):
        conditions = evaluation.asserts.get(name)
        if not conditions:
            gaps.append(f"{name!r} does not run")
        elif not all(value for _, value in conditions):
            gaps.append(f"{name!r} would fail: {[c for c, v in conditions if not v]!r}")
    launched = evaluation.hyprland_actions & LAUNCH_ACTIONS
    if launched:
        gaps.append(f"the Hyprland component would launch or run something: {sorted(launched)!r}")
    return gaps


def test_v1_host_composes_existing_targets_once() -> None:
    v1 = playbook_closure(ROOT, V1_HOST)
    lab = playbook_closure(ROOT, "playbooks/lab.yml")
    assert v1.files == [
        "v1-host.yml",
        "lab.yml",
        "foundation.yml",
        "host-desktop-hyprland.yml",
        "host-sleep-guard.yml",
    ], v1.files
    roles = [(name, entry_vars) for name, entry_vars, _, _ in v1.roles]
    lab_roles = [(name, entry_vars) for name, entry_vars, _, _ in lab.roles]
    assert roles == lab_roles + [
        ("brick_guard", {"brick_guard_brick": "host_desktop_hyprland"}),
        ("host_desktop_hyprland", {}),
        ("brick_guard", {"brick_guard_brick": "host_sleep_guard"}),
        ("host_sleep_guard", {}),
    ], roles
    names = [name for name, _ in roles if name != "brick_guard"]
    assert len(names) == len(set(names)), names
    # The entrypoint reuses the component playbooks and copies nothing.
    assert {source for *_, source in v1.roles} == set(v1.files[1:])
    plays = yaml.load((ROOT / V1_HOST).read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    assert plays[2] == RESIDENT_REFRESH_PLAY
    imports = [play for index, play in enumerate(plays) if index != 2]
    assert len(plays) == 4
    assert all("import_playbook" in play and set(play) <= IMPORT_KEYS for play in imports)


def test_v1_host_lifecycle_opt_in_is_scoped() -> None:
    plays = yaml.load((ROOT / V1_HOST).read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    scoped = {play["import_playbook"]: play.get("vars") for play in plays if "import_playbook" in play}
    assert scoped == {
        "lab.yml": None,
        "host-desktop-hyprland.yml": {LIFECYCLE: True},
        "host-sleep-guard.yml": None,
    }, scoped
    assert scoped["host-desktop-hyprland.yml"][LIFECYCLE] is True
    defaults = load_yaml("roles/host_desktop_hyprland/defaults/main.yml")
    assert defaults[LIFECYCLE] is False, "the opt-in must stay off by default"
    # Only the Hyprland component's play sees the opt-in; no other play in
    # the closure sets or inherits it.
    for name, _, scope, source in playbook_closure(ROOT, V1_HOST).roles:
        assert (LIFECYCLE in scope) == (source == "host-desktop-hyprland.yml"), (name, source, scope)


def test_v1_host_stages_managed_lifecycle() -> None:
    evaluation = evaluate_playbook(ROOT, V1_HOST)
    gaps = managed_lifecycle_gaps(evaluation)
    assert not gaps, gaps
    guard = {(item.action, item.dest) for item in evaluation.staged if item.role == "host_sleep_guard"}
    assert {
        ("template", "/etc/systemd/system/hyperlab-vfio-inhibit@.service"),
        ("copy", "/etc/libvirt/hooks/qemu.d/60-hyperlab-vfio-sleep-guard"),
    } <= guard, guard
    # The bare component import keeps the lifecycle off and must not pass.
    bare = managed_lifecycle_gaps(evaluate_playbook(ROOT, "playbooks/host-desktop-hyprland.yml"))
    assert any("not a YAML true" in gap for gap in bare), bare
    assert any("managed catalog does not receive" in gap for gap in bare), bare
    assert any("Quickshell is not coupled" in gap for gap in bare), bare


def write_fixture(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def refused(root: Path, entry: str, reason: str) -> None:
    try:
        playbook_closure(root, entry)
    except ImportRefused as exc:
        assert reason in str(exc), (reason, str(exc))
    else:
        raise AssertionError(f"{entry} was accepted; expected refusal: {reason}")


def test_import_resolver_refusals() -> None:
    play = "- name: P\n  hosts: hypervisor\n  roles:\n    - {role}\n"

    def imports(*names: str) -> str:
        return "".join(f"- name: I {n}\n  import_playbook: {n}\n" for n in names)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        write_fixture(
            root,
            {
                "outside.yml": play.format(role="escaped"),
                "playbooks/child.yml": play.format(role="child_role"),
                "playbooks/other.yml": play.format(role="other_role"),
                "playbooks/ok.yml": (
                    "# - name: Commented\n#   import_playbook: other.yml\n"
                    "#   roles: [other_role]\n" + imports("child.yml")
                ),
                "playbooks/missing.yml": imports("absent.yml"),
                "playbooks/escape.yml": imports("../outside.yml"),
                "playbooks/absolute.yml": imports(str(root / "playbooks/child.yml")),
                "playbooks/templated.yml": imports('"{{ target }}.yml"'),
                "playbooks/repeat.yml": imports("child.yml", "child.yml"),
                "playbooks/cycle-a.yml": imports("cycle-b.yml"),
                "playbooks/cycle-b.yml": imports("cycle-a.yml"),
                "playbooks/self.yml": imports("self.yml"),
                "playbooks/linked.yml": imports("link.yml"),
                "playbooks/duplicate.yml": (
                    "- name: D\n  import_playbook: child.yml\n  import_playbook: other.yml\n"
                ),
                "playbooks/tasks.yml": (
                    "- name: T\n  hosts: hypervisor\n  roles: [child_role]\n"
                    "  tasks:\n    - ansible.builtin.include_role:\n        name: hidden\n"
                ),
                "playbooks/extra.yml": (
                    "- name: E\n  import_playbook: child.yml\n  when: true\n"
                ),
            },
        )
        (root / "playbooks/link.yml").symlink_to("child.yml")
        (root / "playbooks/entry-link.yml").symlink_to("ok.yml")

        accepted = playbook_closure(root, "playbooks/ok.yml")
        assert accepted.files == ["ok.yml", "child.yml"], accepted.files
        # A file name or role in a comment is not part of the closure.
        assert [name for name, *_ in accepted.roles] == ["child_role"], accepted.roles

        refused(root, "playbooks/missing.yml", "does not exist")
        refused(root, "playbooks/escape.yml", "escapes")
        refused(root, "playbooks/absolute.yml", "absolute import")
        refused(root, "playbooks/templated.yml", "not a plain file name")
        refused(root, "playbooks/repeat.yml", "imported twice")
        refused(root, "playbooks/cycle-a.yml", "cyclic import")
        refused(root, "playbooks/self.yml", "cyclic import")
        refused(root, "playbooks/linked.yml", "redirected by a symlink")
        refused(root, "playbooks/entry-link.yml", "not a regular file")
        refused(root, "playbooks/duplicate.yml", "duplicate YAML key")
        refused(root, "playbooks/tasks.yml", "play carries ['tasks']")
        refused(root, "playbooks/extra.yml", "import carries ['when']")


def test_vfio_is_the_managed_loader_default() -> None:
    tasks = (ROOT / "roles/vfio_boot/tasks/main.yml").read_text(encoding="utf-8")
    assert "line: default Arch-Linux-Hardened-Vfio.conf" in tasks
    assert "line: default Arch-Linux-Hardened.conf" not in tasks
    assert "Make VFIO the normal laboratory boot path" in tasks


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"playbook topology contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
