#!/usr/bin/env python3
"""C10 product GPU policy intent versus root-owned observation contract."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "tools/hyperlabctl"),
)

sys.path.insert(
    0,
    str(ROOT / "tools/hyperlabctl/tests"),
)

import world
from hyperlabctl.providers import domains as domains_module
from hyperlabctl.providers.domains import (
    DomainProvider,
    observe_managed_gpu_policies,
)


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


def domain_row(
    ctx,
) -> tuple[dict, list[dict]]:
    provider = DomainProvider()
    rows = provider.collect(
        ctx
    )

    require(
        len(rows) == 1,
        "product policy test expected exactly one domain",
    )

    return (
        rows[0],
        provider.problems(
            ctx,
            rows,
        ),
    )


def verify_observer_shape() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-policy-observer-"
    ) as temporary:
        root = Path(
            temporary
        )

        directory = root / "domains.d"
        directory.mkdir(
            mode=0o755
        )
        directory.chmod(
            0o755
        )

        target = (
            directory
            / "services-workload-01.conf"
        )

        target.write_text(
            "services-workload-01 dev\n",
            encoding="utf-8",
        )
        target.chmod(
            0o644
        )

        policies, state = (
            observe_managed_gpu_policies(
                directory,
                TRUST,
                expected_uid=os.geteuid(),
            )
        )

        require(
            state == "ok"
            and policies
            == {
                "services-workload-01": "dev",
            },
            "valid managed policy was not observed",
        )

        target.write_text(
            "services-workload-01 dirty\n",
            encoding="utf-8",
        )

        policies, state = (
            observe_managed_gpu_policies(
                directory,
                TRUST,
                expected_uid=os.geteuid(),
            )
        )

        require(
            state == "ok"
            and policies[
                "services-workload-01"
            ]
            == "dirty",
            "observer invented requested metadata "
            "instead of reading root policy",
        )

        target.unlink()

        redirected = root / "redirected"
        redirected.write_text(
            "services-workload-01 dev\n",
            encoding="utf-8",
        )

        target.symlink_to(
            redirected
        )

        policies, state = (
            observe_managed_gpu_policies(
                directory,
                TRUST,
                expected_uid=os.geteuid(),
            )
        )

        require(
            policies == {}
            and state == "unsafe",
            "redirected managed policy was trusted",
        )


def verify_domain_telemetry() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-policy-domain-"
    ) as temporary:
        root = Path(
            temporary
        )

        directory = root / "domains.d"
        directory.mkdir(
            mode=0o755
        )
        directory.chmod(
            0o755
        )

        target = (
            directory
            / "services-workload-01.conf"
        )

        target.write_text(
            "services-workload-01 dev\n",
            encoding="utf-8",
        )
        target.chmod(
            0o644
        )

        ctx = world.build(
            domains=[
                {
                    "name": "services-workload-01",
                    "state": "running",
                    "memory_mb": 1024,
                    "vfio": True,
                    "network": "services",
                    "metadata": world.managed_metadata(
                        "services",
                        "vfio",
                        product_machine=True,
                        gpu_handoff_profile="dev",
                        image_sha256="a" * 64,
                    ),
                }
            ]
        )

        ctx.config.gpu_handoff_managed_dir = str(
            directory
        )

        original = (
            domains_module.observe_managed_gpu_policies
        )

        def observe_as_test_user(
            observed_directory,
            trust_levels,
        ):
            return original(
                observed_directory,
                trust_levels,
                expected_uid=os.geteuid(),
            )

        domains_module.observe_managed_gpu_policies = (
            observe_as_test_user
        )

        try:
            row, problems = domain_row(
                ctx
            )

            require(
                row["gpu_handoff_profile"]
                == "dev",
                "requested GPU handoff metadata was lost",
            )

            require(
                row["gpu_trust_profile"]
                == "dev"
                and row["gpu_policy_state"]
                == "verified",
                "verified root policy was not published",
            )

            require(
                not any(
                    problem["id"]
                    == "domains.gpu_policy_unverified"
                    for problem in problems
                ),
                "verified root policy was reported unverified",
            )

            target.unlink()

            row, problems = domain_row(
                ctx
            )

            require(
                row["gpu_handoff_profile"]
                == "dev"
                and row["gpu_trust_profile"]
                is None
                and row["gpu_policy_state"]
                == "missing",
                "missing root policy was replaced "
                "with metadata intent",
            )

            require(
                any(
                    problem["id"]
                    == "domains.gpu_policy_unverified"
                    for problem in problems
                ),
                "missing root policy was not diagnosed",
            )

            target.write_text(
                "services-workload-01 dirty\n",
                encoding="utf-8",
            )
            target.chmod(
                0o644
            )

            row, problems = domain_row(
                ctx
            )

            require(
                row["gpu_handoff_profile"]
                == "dev"
                and row["gpu_trust_profile"]
                == "dirty"
                and row["gpu_policy_state"]
                == "mismatch",
                "root policy mismatch was hidden",
            )

            require(
                any(
                    problem["id"]
                    == "domains.gpu_policy_unverified"
                    for problem in problems
                ),
                "root policy mismatch was not diagnosed",
            )

        finally:
            domains_module.observe_managed_gpu_policies = (
                original
            )


def main() -> int:
    verify_observer_shape()
    verify_domain_telemetry()

    print(
        "C10 root GPU policy observability contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
