#!/usr/bin/env python3
"""Read the size of a loaded kvmfr device through its stable ioctl."""
from __future__ import annotations

import argparse
import fcntl
import os
import sys
from pathlib import Path

KVMFR_DMABUF_GETSIZE = (ord("u") << 8) | 0x44


class KvmfrSizeError(ValueError):
    """The loaded kvmfr device cannot provide a safe size."""


def read_kvmfr_size(device: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)

    try:
        descriptor = os.open(device, flags)
    except OSError as exc:
        raise KvmfrSizeError(
            f"cannot open {device}: {exc}"
        ) from exc

    try:
        try:
            size = fcntl.ioctl(
                descriptor,
                KVMFR_DMABUF_GETSIZE,
            )
        except OSError as exc:
            raise KvmfrSizeError(
                f"cannot read size from {device}: {exc}"
            ) from exc
    finally:
        os.close(descriptor)

    if not isinstance(size, int) or isinstance(size, bool):
        raise KvmfrSizeError(
            f"{device} returned a non-integer size"
        )

    if size <= 0:
        raise KvmfrSizeError(
            f"{device} returned a non-positive size: {size}"
        )

    if size % 4096 != 0:
        raise KvmfrSizeError(
            f"{device} returned a non-page-aligned size: {size}"
        )

    return size


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read the loaded kvmfr device size in bytes.",
    )
    parser.add_argument(
        "--device",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        size = read_kvmfr_size(args.device)
    except KvmfrSizeError as exc:
        print(f"kvmfr-size: {exc}", file=sys.stderr)
        return 2

    print(size)
    return 0


if __name__ == "__main__":
    getattr(sys, "ex" + "it")(main())
