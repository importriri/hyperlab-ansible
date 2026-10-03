#!/usr/bin/env python3
"""C10 network identity versus GPU handoff policy contract."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "tools/hyperlabctl"),
)

from hyperlabctl.providers.domains import (
    DomainProvider,
    network_identity,
    resolve_trust,
)


DECLARED = {
    "clean",
    "dirty",
    "dev",
    "lab",
    "services",
}


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def managed(
    name: str,
    network: str,
) -> dict:
    return {
        "name": name,
        "managed": True,
        "network_profile": network,
        "networks": [network],
    }


def main() -> int:
    services = managed(
        "services-workload-01",
        "services",
    )

    gpu_profiles = {
        "services-workload-01": "dev",
    }

    require(
        network_identity(
            services,
            DECLARED,
        )
        == "services",
        "SERVICES network identity was lost",
    )

    trust, source = resolve_trust(
        services,
        gpu_profiles,
        DECLARED,
    )

    require(
        trust == "services"
        and source == "network-profile",
        "GPU handoff policy reclassified "
        "managed SERVICES identity",
    )

    dev = managed(
        "arch-dev-managed",
        "dev",
    )

    trust, source = resolve_trust(
        dev,
        {
            "arch-dev-managed": "dev",
        },
        DECLARED,
    )

    require(
        trust == "dev"
        and source == "network-profile",
        "matching managed DEV identity changed",
    )

    legacy = {
        "name": "arch-dev-vfio",
        "managed": False,
        "network_profile": None,
        "networks": [],
    }

    trust, source = resolve_trust(
        legacy,
        {
            "arch-dev-vfio": "dev",
        },
        DECLARED,
    )

    require(
        trust == "dev"
        and source == "gpu-domain-profile",
        "legacy unmanaged GPU-profile "
        "fallback was broken",
    )

    mismatched_attachment = {
        "name": "managed-bad-attachment",
        "managed": True,
        "network_profile": "services",
        "networks": ["dev"],
    }

    trust, source = resolve_trust(
        mismatched_attachment,
        {
            "managed-bad-attachment": "dev",
        },
        DECLARED,
    )

    require(
        trust is None
        and source is None,
        "managed guest with mismatched "
        "network attachment gained identity",
    )

    problems = DomainProvider().problems(
        None,
        [
            {
                "name": "services-workload-01",
                "vfio": True,
                "managed": True,
                "gpu_handoff_profile": "dev",
                "gpu_trust_profile": "dev",
                "network_profile": "services",
                "trust_source": None,
                "networks": ["dev"],
            }
        ],
    )

    require(
        any(
            problem["id"]
            == "domains.network_identity_mismatch"
            for problem in problems
        ),
        "network attachment mismatch "
        "was not reported",
    )

    require(
        not any(
            problem["id"]
            == "domains.trust_conflict"
            for problem in problems
        ),
        "GPU handoff profile was still "
        "treated as network identity",
    )

    print(
        "C10 GPU policy / network identity contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
