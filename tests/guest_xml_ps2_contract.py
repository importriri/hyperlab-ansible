#!/usr/bin/env python3
"""Fail-closed contract for the VFIO PS/2 feature."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/guest_xml_contract.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "guest_xml_contract_ps2",
        TOOL,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_domain(path: Path, ps2_state: str | None) -> None:
    feature = (
        ""
        if ps2_state is None
        else f'<ps2 state="{ps2_state}"/>'
    )

    path.write_text(
        "<domain>"
        "<features>"
        + feature
        + "</features>"
        "<devices/>"
        "</domain>\n",
        encoding="utf-8",
    )


def main() -> int:
    module = load_tool()

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        off = root / "off.xml"
        on = root / "on.xml"
        absent = root / "absent.xml"

        write_domain(off, "off")
        write_domain(on, "on")
        write_domain(absent, None)

        off_signature = module.signature(off)
        on_signature = module.signature(on)
        absent_signature = module.signature(absent)

        assert off_signature["ps2"] == "off"
        assert on_signature["ps2"] == "on"
        assert absent_signature["ps2"] is None

        assert module.contract_value_matches(
            "ps2",
            off_signature,
            off_signature,
            False,
        )

        assert not module.contract_value_matches(
            "ps2",
            off_signature,
            on_signature,
            False,
        )

        assert not module.contract_value_matches(
            "ps2",
            off_signature,
            absent_signature,
            False,
        )

    print("guest XML PS/2 contract: OK")
    return 0


if __name__ == "__main__":
    main()
