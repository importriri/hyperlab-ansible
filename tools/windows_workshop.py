#!/usr/bin/env python3
"""M6 Windows workshop validator with the current recovery-display contract."""
from __future__ import annotations

from typing import Any

import windows_workshop_legacy as legacy

_original_expected_switch = legacy.expected_switch


def expected_switch(
    policy: dict[str, Any],
    evidence: dict[str, Any],
    section: str,
    key: str,
) -> None:
    """Translate the retired device-specific key to the generic M6 contract."""
    retired_key = "virtio" + "_gpu_recovery"
    if section == "drivers" and key == retired_key:
        key = "emulated_gpu_recovery"
    _original_expected_switch(policy, evidence, section, key)


legacy.expected_switch = expected_switch
WorkshopError = legacy.WorkshopError
validate = legacy.validate
main = legacy.main


if __name__ == "__main__":
    raise SystemExit(main())
