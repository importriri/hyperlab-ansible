#!/usr/bin/env python3
"""C10 root-owned GPU handoff policy materialization contract."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/gpu_handoff_policy.py"


TRUST = {
    "clean": 3,
    "dev": 2,
    "dirty": 1,
    "lab": 0,
}


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def invoke(
    directory: Path,
    static_file: Path,
    action: str,
    payload: dict,
    *,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        str(TOOL),
        action,
        "--directory",
        str(directory),
        "--static-domains",
        str(static_file),
        "--trust-levels-json",
        json.dumps(
            TRUST,
            sort_keys=True,
        ),
    ]

    if dry_run:
        argv.append(
            "--dry-run"
        )

    return subprocess.run(
        argv,
        input=json.dumps(
            payload
        ),
        text=True,
        capture_output=True,
        check=False,
    )


def payload(
    name: str = "services-workload-01",
    profile: str = "dev",
) -> dict:
    return {
        "name": name,
        "device_profile": "vfio",
        "gpu_handoff_profile": profile,
        "network_profile": "services",
        "tags": [
            "managed-machine",
            "linux",
            "services",
            "vfio",
        ],
    }


def verify_policy_tool() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-gpu-policy-"
    ) as temporary:
        root = Path(
            temporary
        )

        directory = (
            root / "domains.d"
        )

        directory.mkdir(
            mode=0o755
        )

        directory.chmod(
            0o755
        )

        static_file = (
            root / "domains"
        )

        static_file.write_text(
            "# fixture GPU handoff policy\n"
            "arch-dev-vfio dev\n"
            "win11clean-valley clean\n",
            encoding="utf-8",
        )

        static_file.chmod(
            0o644
        )

        request = payload()

        claim_request = payload(
            name="services-gpu-claim",
            profile="dev",
        )

        claim_target = (
            directory
            / "services-gpu-claim.conf"
        )

        claimed = invoke(
            directory,
            static_file,
            "create",
            claim_request,
        )

        require(
            claimed.returncode == 0,
            claimed.stderr,
        )

        claim_result = json.loads(
            claimed.stdout
        )

        require(
            claim_result["changed"] is True
            and claim_result["status"] == "created",
            "create-only policy claim did not "
            "report transaction ownership",
        )

        require(
            claim_target.read_text(
                encoding="utf-8"
            )
            == "services-gpu-claim dev\n",
            "create-only policy claim "
            "published the wrong payload",
        )

        duplicate_claim = invoke(
            directory,
            static_file,
            "create",
            claim_request,
        )

        require(
            duplicate_claim.returncode == 2,
            "a new transaction claimed "
            "a pre-existing managed policy",
        )

        require(
            claim_target.read_text(
                encoding="utf-8"
            )
            == "services-gpu-claim dev\n",
            "refused duplicate claim "
            "modified the pre-existing policy",
        )

        claim_cleanup = invoke(
            directory,
            static_file,
            "remove",
            claim_request,
        )

        require(
            claim_cleanup.returncode == 0
            and not claim_target.exists(),
            "create-only policy test cleanup failed",
        )

        first = invoke(
            directory,
            static_file,
            "ensure",
            request,
        )

        require(
            first.returncode == 0,
            first.stderr,
        )

        result = json.loads(
            first.stdout
        )

        require(
            result["changed"] is True,
            "first policy materialization "
            "did not report a change",
        )

        target = (
            directory
            / "services-workload-01.conf"
        )

        require(
            target.read_text(
                encoding="utf-8"
            )
            == "services-workload-01 dev\n",
            "managed policy payload changed",
        )

        info = target.lstat()

        require(
            stat.S_ISREG(
                info.st_mode
            )
            and not stat.S_ISLNK(
                info.st_mode
            ),
            "managed policy is not "
            "a real regular file",
        )

        require(
            info.st_uid == os.geteuid(),
            "managed policy ownership changed",
        )

        require(
            stat.S_IMODE(
                info.st_mode
            )
            == 0o644,
            "managed policy mode is not 0644",
        )

        second = invoke(
            directory,
            static_file,
            "ensure",
            request,
        )

        require(
            second.returncode == 0,
            second.stderr,
        )

        require(
            json.loads(
                second.stdout
            )["changed"]
            is False,
            "idempotent ensure reported drift",
        )

        verified = invoke(
            directory,
            static_file,
            "verify",
            request,
        )

        require(
            verified.returncode == 0,
            verified.stderr,
        )

        changed = payload(
            profile="dirty"
        )

        preview = invoke(
            directory,
            static_file,
            "ensure",
            changed,
            dry_run=True,
        )

        require(
            preview.returncode == 0,
            preview.stderr,
        )

        require(
            json.loads(
                preview.stdout
            )["changed"]
            is True,
            "dry-run did not predict "
            "a policy change",
        )

        require(
            target.read_text(
                encoding="utf-8"
            )
            == "services-workload-01 dev\n",
            "dry-run changed root policy",
        )

        applied = invoke(
            directory,
            static_file,
            "ensure",
            changed,
        )

        require(
            applied.returncode == 0,
            applied.stderr,
        )

        require(
            target.read_text(
                encoding="utf-8"
            )
            == "services-workload-01 dirty\n",
            "reviewed policy update "
            "was not materialized",
        )

        collision = invoke(
            directory,
            static_file,
            "ensure",
            payload(
                name="arch-dev-vfio",
                profile="dev",
            ),
        )

        require(
            collision.returncode == 2,
            "managed policy collided "
            "with a fixture domain",
        )

        unreviewed = payload(
            profile="dev"
        )

        unreviewed[
            "gpu_handoff_profile"
        ] = "services"

        refused = invoke(
            directory,
            static_file,
            "ensure",
            unreviewed,
        )

        require(
            refused.returncode == 2,
            "unreviewed GPU profile "
            "was accepted",
        )

        not_machine = payload()
        not_machine["tags"] = [
            "linux",
            "services",
        ]

        refused = invoke(
            directory,
            static_file,
            "ensure",
            not_machine,
        )

        require(
            refused.returncode == 2,
            "non-Machine VM gained dynamic "
            "GPU policy authority",
        )

        removed = invoke(
            directory,
            static_file,
            "remove",
            changed,
        )

        require(
            removed.returncode == 0,
            removed.stderr,
        )

        require(
            json.loads(
                removed.stdout
            )["changed"]
            is True
            and not target.exists(),
            "managed policy was not removed",
        )

        target.symlink_to(
            static_file
        )

        refused = invoke(
            directory,
            static_file,
            "ensure",
            request,
        )

        require(
            refused.returncode == 2,
            "symlinked managed policy "
            "target was accepted",
        )


def verify_source_wiring() -> None:
    hook = (
        ROOT
        / "roles/gpu_handoff/files/qemu"
    ).read_text(
        encoding="utf-8"
    )

    require(
        "GPU_HANDOFF_MANAGED_DIR"
        in hook,
        "qemu hook ignores managed Machine policy",
    )

    role = (
        ROOT
        / "roles/gpu_handoff/tasks/main.yml"
    ).read_text(
        encoding="utf-8"
    )

    require(
        "/etc/gpu-handoff/domains.d"
        in role,
        "gpu_handoff brick does not own "
        "the managed policy directory",
    )

    defaults = (
        ROOT
        / "roles/guest/defaults/main.yml"
    ).read_text(
        encoding="utf-8"
    )

    require(
        "guest_gpu_handoff_policy_tool"
        in defaults,
        "guest lifecycle has no "
        "privileged policy bridge",
    )

    for relative in (
        "roles/guest/tasks/create.yml",
        "roles/guest/tasks/start.yml",
        "roles/guest/tasks/reset.yml",
        "roles/guest/tasks/power-cycle.yml",
        "roles/guest/tasks/validate.yml",
        "roles/guest/tasks/destroy.yml",
    ):
        source = (
            ROOT / relative
        ).read_text(
            encoding="utf-8"
        )

        require(
            "vfio-policy.yml"
            in source,
            f"{relative} is missing "
            "the managed GPU policy boundary",
        )

    create_source = (
        ROOT
        / "roles/guest/tasks/create.yml"
    ).read_text(
        encoding="utf-8"
    )

    require(
        "guest_gpu_handoff_policy_action: create"
        in create_source,
        "new Machine transaction does not "
        "use create-only GPU policy claim",
    )

    require(
        "guest_gpu_handoff_policy_created_by_transaction"
        in create_source,
        "new Machine transaction does not "
        "record GPU policy ownership",
    )

    normalized_create_source = " ".join(
        create_source.split()
    )

    require(
        "guest_gpu_handoff_policy_created_by_transaction "
        "| default(false) | bool"
        in normalized_create_source,
        "create rescue does not require "
        "transaction-owned GPU policy",
    )


def main() -> int:
    verify_policy_tool()
    verify_source_wiring()

    print(
        "C10 privileged GPU policy "
        "materialization contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
