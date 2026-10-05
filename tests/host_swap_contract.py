#!/usr/bin/env python3
"""Host swap never backs guest memory with an unencrypted disk (milestone 10).

The base role reads /proc/swaps and refuses any swap device that is not
zram or a dm-crypt mapping. This contract runs that exact pattern against
the shapes /proc/swaps reports.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    tasks = yaml.safe_load((ROOT / "roles/base/tasks/main.yml").read_text())
    names = [task["name"] for task in tasks]
    read = names.index("Read the active swap devices")
    guard = tasks[names.index("Refuse swap on an unencrypted device")]
    require(read < names.index("Refuse swap on an unencrypted device"), "the guard runs before the read")
    require(tasks[read]["ansible.builtin.slurp"]["src"] == "/proc/swaps", "the guard reads something else")
    condition = guard["ansible.builtin.assert"]["that"][0]
    pattern = re.search(r"match\('(.+)'\)", condition).group(1)
    for device, accepted in (("/dev/zram0", True), ("/dev/zram12", True), ("/dev/mapper/cryptswap", True),
                             ("/dev/nvme0n1p3", False), ("/dev/sda2", False), ("/swap/swapfile", False),
                             ("/dev/mapper/../sda2", False), ("/dev/zram", False)):
        require((re.match(pattern, device) is not None) is accepted,
                f"swap on {device} was {'refused' if accepted else 'accepted'}")
    print("Host swap contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
