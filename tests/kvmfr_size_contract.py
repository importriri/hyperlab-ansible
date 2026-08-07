#!/usr/bin/env python3
"""Contract tests for the runtime kvmfr size probe."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/kvmfr_size.py"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kvmfr_size",
        TOOL,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_probe(
    module: ModuleType,
    result: Any,
) -> tuple[int, list[int], list[int]]:
    opened: list[int] = []
    closed: list[int] = []

    real_open = module.os.open
    real_close = module.os.close
    real_ioctl = module.fcntl.ioctl

    def fake_open(path: Path, flags: int) -> int:
        assert path == Path("/dev/kvmfr0")
        opened.append(flags)
        return 17

    def fake_close(descriptor: int) -> None:
        closed.append(descriptor)

    def fake_ioctl(descriptor: int, request: int) -> Any:
        assert descriptor == 17
        assert request == module.KVMFR_DMABUF_GETSIZE
        return result

    module.os.open = fake_open
    module.os.close = fake_close
    module.fcntl.ioctl = fake_ioctl

    try:
        observed = module.read_kvmfr_size(
            Path("/dev/kvmfr0"),
        )
    finally:
        module.os.open = real_open
        module.os.close = real_close
        module.fcntl.ioctl = real_ioctl

    return observed, opened, closed


def main() -> None:
    module = load_tool()

    assert module.KVMFR_DMABUF_GETSIZE == 0x7544

    observed, opened, closed = run_probe(
        module,
        64 * 1024 * 1024,
    )
    assert observed == 67_108_864
    assert len(opened) == 1
    assert closed == [17]

    for bad in (0, -1, 4097, "67108864", True):
        try:
            run_probe(module, bad)
        except module.KvmfrSizeError:
            pass
        else:
            raise AssertionError(
                f"unsafe kvmfr size accepted: {bad!r}"
            )

    print("kvmfr runtime size contract: OK")


if __name__ == "__main__":
    main()
