#!/usr/bin/env python3
"""Structural contract for the non-destructive image_store brick."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/image_store"
TASKS = ROLE / "tasks"

FORBIDDEN_TEXT = (
    "qemu-img create",
    "qemu-img convert",
    "qemu-img rebase",
    "qemu-img commit",
    "virsh define",
    "virsh create",
    "virsh start",
    "virsh destroy",
    "virsh undefine",
    "rm -rf",
    "chmod -r",
    "chown -r",
    "find -delete",
)

ALLOWED_COMMANDS = {
    "Resolve the root as the kernel would": "/usr/bin/readlink",
    "Read NOCOW attribute from the nearest existing store ancestor": "/usr/bin/lsattr",
    "Verify each non-root runtime identity can traverse its directories": "/usr/bin/runuser",
    "Read NOCOW attribute from the created store root": "/usr/bin/lsattr",
}

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def flatten(tasks: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        found.append(task)
        for section in ("block", "rescue", "always"):
            found.extend(flatten(task.get(section)))
    return found


def check_modes(layout: list[dict[str, Any]]) -> None:
    check(all(len(entry["mode"]) == 4 and entry["mode"][0] == "0" for entry in layout),
          "every mode must be written as four octal digits")
    for base in ("bases", "bases/windows", "bases/linux"):
        mode = next(entry["mode"] for entry in layout if entry["path"] == base)
        check(all(int(digit) & 0o2 == 0 for digit in mode[1:]),
              f"{base} must carry no write bit, got {mode}")
        check(int(mode[3]) & 0o1 != 0, f"{base} must stay traversable, got {mode}")
    root_mode = next(entry["mode"] for entry in layout if entry["path"] == "")
    check(int(root_mode[3]) & 0o1 != 0,
          f"the root must let non-root runtime identities reach their subtree, got {root_mode}")
    expected_access = {"disposable": "qemu", "permanent": "qemu", "cloud-init": "qemu",
                       "nvram": "qemu", "snapshots": "qemu", "tpm": "swtpm"}
    by_path = {entry["path"]: entry for entry in layout}
    for path, access in expected_access.items():
        entry = by_path[path]
        check(entry["access"] == access, f"{path} must use the {access} runtime identity")
        check(int(entry["mode"][2]) & 0o1 != 0,
              f"{path} must grant group traversal, got {entry['mode']}")


def main() -> int:
    storage = load(ROOT / "group_vars/all/storage.yml")
    defaults = load(ROLE / "defaults/main.yml")
    task_files = {path.name: flatten(load(path)) for path in sorted(TASKS.glob("*.yml"))}
    all_tasks = [task for tasks in task_files.values() for task in tasks]
    main_tasks = task_files.get("main.yml", [])
    validate_tasks = task_files.get("validate.yml", [])
    identity_tasks = task_files.get("identity.yml", [])

    check(bool(main_tasks), "roles/image_store/tasks/main.yml has no tasks")
    check(bool(validate_tasks), "roles/image_store/tasks/validate.yml has no tasks")
    check(bool(identity_tasks), "roles/image_store/tasks/identity.yml has no tasks")
    check("nocow-evaluate.yml" in task_files, "NOCOW interpretation must be a testable shared task")

    layout = defaults.get("image_store_layout")
    check(isinstance(layout, list), "image_store_layout must be a list")
    if not isinstance(layout, list) or not all(isinstance(entry, dict) for entry in layout):
        check(False, "every image_store_layout entry must be a mapping")
        layout = []

    required = set(storage["hyperlab_required_directories"])
    paths = [entry.get("path") for entry in layout]
    check(set(paths) == required, f"layout/required directory difference: {set(paths) ^ required}")
    check(len(paths) == len(set(paths)), "the layout contains a duplicate path")
    check(all(isinstance(path, str) and not path.startswith("/") for path in paths),
          "layout paths must be relative strings")
    check(all(".." not in path.split("/") for path in paths if isinstance(path, str)),
          "a layout path contains ..")
    check(all(isinstance(entry.get("purpose"), str) and entry["purpose"] for entry in layout),
          "every directory must state a non-empty purpose")
    check(all(entry.get("access") in {"admin", "qemu", "swtpm"} for entry in layout),
          "every directory must use admin, qemu or swtpm access")

    modes_are_strings = all(isinstance(entry.get("mode"), str) for entry in layout)
    check(modes_are_strings, "every mode must be a quoted string, not a YAML octal integer")
    if modes_are_strings and layout:
        check_modes(layout)

    root = storage["hyperlab_root"]
    check(root.startswith("/"), "hyperlab_root must be absolute")
    check(".." not in root.split("/"), "hyperlab_root must not contain ..")
    check(not root.endswith("/"), "hyperlab_root must not end in a slash")
    forbidden_roots = storage["hyperlab_forbidden_roots"]
    for path in ("/", "/tmp", "/var/lib/libvirt"):
        check(path in forbidden_roots, f"{path} must be refused as a root")

    sentinel = storage.get("hyperlab_runtime_identity_unset")
    check(isinstance(sentinel, str) and sentinel.startswith("__") and sentinel.endswith("__"),
          "the runtime identity sentinel must be unmistakably invalid")
    for key in ("hyperlab_qemu_user_declared", "hyperlab_qemu_group_declared",
                "hyperlab_swtpm_user_declared", "hyperlab_swtpm_group_declared"):
        check(storage.get(key) == sentinel,
              f"{key} must remain a blocking hardware sentinel in shared data")

    sizes = [load(path).get("virtual_size_gib", 0) for path in sorted((ROOT / "images").glob("*.yml"))]
    if sizes:
        expected = -(-int(max(sizes) * 3) // 2)
        check(defaults.get("image_store_capacity_plan_gib", 0) >= expected,
              f"capacity plan must be at least {expected} GiB")
    check(not [task for task in main_tasks if "ansible.builtin.assert" in task and "size_available" in yaml.safe_dump(task)],
          "M2 must warn about future capacity, not refuse empty-directory creation")

    source_paths = [path for path in ROLE.rglob("*") if path.is_file()]
    source_paths.append(ROOT / "playbooks/image-store.yml")
    source_text = "\n".join(path.read_text(errors="replace") for path in sorted(source_paths)).lower()
    for command in FORBIDDEN_TEXT:
        check(command not in source_text, f"the brick must not contain destructive operation `{command}`")

    for task in all_tasks:
        for module in ("ansible.builtin.file", "file", "ansible.builtin.copy", "copy"):
            arguments = task.get(module)
            if isinstance(arguments, dict):
                check(not arguments.get("recurse"),
                      f"task {task.get('name')!r} sets recurse and could rewrite existing images")

    writing = {"ansible.builtin.file", "file", "ansible.builtin.copy", "copy",
               "ansible.builtin.template", "template", "ansible.builtin.lineinfile", "lineinfile",
               "ansible.builtin.blockinfile", "blockinfile"}
    for task in validate_tasks:
        used = set(task) & writing
        check(not used, f"validate.yml must not write, but {task.get('name')!r} uses {used}")

    for task in all_tasks:
        check("ansible.builtin.shell" not in task and "shell" not in task,
              f"task {task.get('name')!r} uses shell; image_store permits no shell")
        command = task.get("ansible.builtin.command") or task.get("command")
        if command is None:
            continue
        name = task.get("name", "")
        expected_executable = ALLOWED_COMMANDS.get(name)
        check(expected_executable is not None, f"task {name!r} shells out but is not allowlisted")
        check(isinstance(command, dict) and isinstance(command.get("argv"), list),
              f"allowlisted command task {name!r} must use argv")
        if isinstance(command, dict) and isinstance(command.get("argv"), list) and command["argv"]:
            check(command["argv"][0] == expected_executable,
                  f"task {name!r} must execute {expected_executable}")
        check(task.get("changed_when") is False,
              f"read-only command task {name!r} must set changed_when: false")

    command_names = {task.get("name") for task in all_tasks
                     if "ansible.builtin.command" in task or "command" in task}
    check(command_names == set(ALLOWED_COMMANDS),
          f"command allowlist and role differ: {command_names ^ set(ALLOWED_COMMANDS)}")

    order = [task.get("ansible.builtin.include_tasks") for task in main_tasks]
    check("identity.yml" in order and "validate.yml" in order,
          "main.yml must include identity.yml and validate.yml")
    creates = next((index for index, task in enumerate(main_tasks)
                    if "ansible.builtin.file" in task), len(main_tasks))
    if "validate.yml" in order:
        check(order.index("validate.yml") < creates, "validation must run before directory creation")

    validate_text = (TASKS / "validate.yml").read_text()
    identity_text = (TASKS / "identity.yml").read_text()
    main_text = (TASKS / "main.yml").read_text()
    nocow_text = (TASKS / "nocow-evaluate.yml").read_text()
    check("/usr/bin/readlink" in validate_text, "validation must canonicalise every existing ancestor")
    check("stat.dev" in validate_text and "stat.dev" in main_text,
          "mount boundaries must be checked before and after creation")
    check("hyperlab_required_directories" in validate_text,
          "runtime overrides must be checked against the independent required set")
    check("rejectattr('ansible_facts', 'defined')" in identity_text,
          "identity refusal must inspect getent results")
    check("swtpm_user" in identity_text and "swtpm_group" in identity_text,
          "swtpm needs its own runtime identity")
    check("/usr/bin/runuser" in main_text and "/usr/bin/test" in main_text,
          "the role must prove runtime traversal under the configured identity")
    for field in ("stat.pw_name", "stat.gr_name", "stat.mode", "stat.dev"):
        check(field in main_text, f"post-creation condition must verify {field}")
    check("regex_replace" not in nocow_text and ".split()" in nocow_text,
          "NOCOW detection must inspect only lsattr's attribute field")
    check(defaults.get("image_store_require_nocow") is True,
          "Btrfs NOCOW must be strict by default")
    check(main_text.index("Read NOCOW attribute from the nearest existing store ancestor")
          < main_text.index("Create each store directory individually"),
          "the NOCOW inheritance gate must run before the first directory write")
    check("when: not ansible_check_mode" in main_text,
          "real post-conditions and manifest writes must be guarded in check mode")
    check("CHECK MODE:" in main_text, "check mode must state the deferred boundary")
    check("Read NOCOW attribute from the created store root" in main_text,
          "a real run must verify inherited NOCOW")

    play = load(ROOT / "playbooks/image-store.yml")[0]
    role_names = [entry["role"] if isinstance(entry, dict) else entry for entry in play["roles"]]
    check(role_names == ["brick_guard", "image_store"],
          f"image-store.yml must mount only the guard and brick, got {role_names}")
    bricks = load(ROOT / "group_vars/all/bricks.yml")
    check(bricks["brick_requires"].get("image_store") == ["kvm_host"],
          "image_store must depend on kvm_host")
    check(bricks["brick_playbooks"].get("image_store") == "playbooks/image-store.yml",
          "brick graph must name the image-store playbook")

    if errors:
        print("IMAGE STORE CONTRACT FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"image store contract: OK ({len(layout)} directories, {len(all_tasks)} tasks inspected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
