#!/usr/bin/env python3
"""A sealed image is read-only and verified by digest at every use.

A Golden Image in the store is used in three ways, and each one checks it:

  1. a disposable Machine's disk is a qcow2 overlay over the sealed base, so
     every guest operation that opens that disk verifies the base first:
     read-only mode and ownership, the store's filesystem, the digest its
     manifest pins, and its provenance receipt. The operations that never
     open the disk are the only ones left out, and the list is derived from
     the role's own supported operations, so a new operation that is not
     classified fails here;
  2. a permanent Machine's disk is an independent clone taken after the same
     verification at create; validation refuses one with a backing file, so
     a permanent Machine never reads the base again;
  3. the Workbench derives an image only from a base whose file still
     matches its sealed digest, and only reads it.

The image factory commits the base as root:qemu 0440, the mode the guest
role requires.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / "roles/guest"

# Operations that never open the disk: they talk to a running domain or
# remove one, and none of them starts QEMU on the disk.
NO_DISK = {"shutdown", "reboot", "stop", "destroy"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_condition(main: str) -> str:
    start = main.index("- name: Verify the sealed base before any operation that depends on it")
    return main[start:main.index("\n- name:", start + 1)]


def check_every_disposable_use() -> None:
    operations = yaml.safe_load((GUEST / "defaults/main.yml").read_text())["guest_supported_operations"]
    unknown = NO_DISK - set(operations)
    require(not unknown, f"classified operations the role no longer has: {sorted(unknown)}")
    block = verify_condition((GUEST / "tasks/main.yml").read_text())
    require("ansible.builtin.include_tasks: verify-base.yml" in block, "verify-base is not included")
    require("guest_operation == 'create' and guest_transaction_clean" in block,
            "a new Machine is not created from a verified base")
    match = re.search(r"guest_plan\.lifecycle == 'disposable' and\s+guest_operation in (\[[^\]]*\])", block)
    require(match is not None, "disposable Machines do not verify their base")
    verified = set(yaml.safe_load(match.group(1)))
    for operation in operations:
        if operation in NO_DISK:
            require(operation not in verified or operation == "create",
                    f"{operation} is classified as not opening the disk")
            continue
        require(operation in verified,
                f"a disposable Machine's {operation} opens its overlay without verifying the base")


def check_base_checks() -> None:
    base = (GUEST / "tasks/verify-base.yml").read_text()
    for needle, why in (
        ("guest_base_stat.stat.mode == '0440'", "the base must be read-only"),
        ("guest_base_stat.stat.pw_name == 'root'", "the base must be owned by root"),
        ("guest_base_stat.stat.gr_name == guest_qemu_group", "QEMU reads the base through its group"),
        ("guest_base_stat.stat.checksum == guest_plan.image_sha256", "the digest is not compared"),
        ("checksum_algorithm: sha256", "the digest is not SHA-256"),
        ("guest_base_stat.stat.dev == guest_store_root_stat.stat.dev", "the base may live outside the store"),
        ("not guest_base_stat.stat.islnk", "a redirected base is accepted"),
        ("guest_image_receipt_guard_tool", "the provenance receipt is not checked"),
        ("guest_base_info.get('backing-filename') is none", "the base may itself be an overlay"),
    ):
        require(needle in base, why)
    prepare = (ROOT / "roles/image_factory/tasks/prepare.yml").read_text()
    protect = prepare.index("- name: Protect the verified base staging file for QEMU read access")
    task = prepare[protect:prepare.index("- name:", protect + 1)]
    require('path: "{{ image_factory_plan.base_new_path }}"' in task and 'mode: "0440"' in task
            and "owner: root" in task, "the image factory does not make the base read-only")
    require(protect < prepare.index("- name: Commit the verified base atomically"),
            "the base is committed before it is read-only")


def check_permanent_is_independent() -> None:
    create = (GUEST / "tasks/create.yml").read_text()
    permanent = create[create.index("- name: Create the independent permanent qcow2 clone"):]
    permanent = permanent[:permanent.index("\n        - name:", 1)]
    require("- convert" in permanent and "- -b" not in permanent,
            "a permanent Machine's disk must be a clone, not an overlay")
    disposable = create[create.index("- name: Create the disposable qcow2 overlay"):]
    disposable = disposable[:disposable.index("\n        - name:", 1)]
    require('- -b\n              - "{{ guest_plan.base_path }}"' in disposable,
            "a disposable overlay must back onto exactly the verified base")
    validate = (GUEST / "tasks/validate.yml").read_text()
    require("guest_plan.lifecycle == 'permanent' and" in validate
            and "'backing-filename' not in guest_disk_chain[0]" in validate,
            "validation accepts a permanent disk that still reads the base")


def check_workbench_derive() -> None:
    source = (ROOT / "tools/workbench.py").read_text()
    derive = source[source.index("def cmd_derive"):source.index("def cmd_discard")]
    require('sha256_file(base) == base_manifest["sha256"]' in derive,
            "a derivation does not verify its base's digest")
    require(derive.index('sha256_file(base) == base_manifest["sha256"]')
            < derive.index('"qemu-img", "convert"'),
            "the base is copied before its digest is checked")
    require('base_manifest.get("status") == "sealed"' in derive, "a derivation accepts an unsealed base")


def main() -> int:
    check_every_disposable_use()
    check_base_checks()
    check_permanent_is_independent()
    check_workbench_derive()
    print("Sealed base use contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
