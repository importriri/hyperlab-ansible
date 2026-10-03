"""hyperlabctl workbench list reads the root-owned registry and refuses bad records."""

import io
import json
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import world
from harness import equals
from hyperlabctl.cli import main

GOOD = {
    "schema_version": 1, "domain": "arch-dev-vfio", "image_id": "arch-dev-20261003",
    "base_image": "arch", "profile": "dev", "state": "captured",
    "adopted_by": "sid", "adopted_at": "2026-10-03T18:00:00+00:00",
    "captured": {"sha256": "a" * 64, "virtual_size_bytes": 1},
}


def _list(root):
    os.environ["HYPERLAB_WORKBENCH_ROOT"] = str(root)
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            code = main(["--json", "workbench", "list"], ctx=world.build(trust=None))
    finally:
        del os.environ["HYPERLAB_WORKBENCH_ROOT"]
    return code, json.loads(buffer.getvalue())


def test_workbench_absent_is_empty_not_an_error():
    with tempfile.TemporaryDirectory() as temporary:
        code, payload = _list(Path(temporary) / "missing")
    equals("absent_exit", code, 0)
    equals("absent_available", payload["available"], False)
    equals("absent_rows", payload["candidates"], [])


def test_workbench_lists_valid_records_and_reports_bad_ones():
    with tempfile.TemporaryDirectory() as temporary:
        registry = Path(temporary) / "registry"
        registry.mkdir()
        (registry / "arch-dev-vfio.json").write_text(json.dumps(GOOD))
        (registry / "renamed.json").write_text(json.dumps(GOOD))
        bad = dict(GOOD, state="captured", captured={"sha256": "nope", "virtual_size_bytes": 1})
        (registry / "bad.json").write_text(json.dumps(dict(bad, domain="bad")))
        (registry / "junk.json").write_text("{")
        _, payload = _list(Path(temporary))
    equals("valid_rows", [row["domain"] for row in payload["candidates"]], ["arch-dev-vfio"])
    equals("valid_digest", payload["candidates"][0]["sha256"], "a" * 64)
    equals("refused_count", len(payload["errors"]), 3)
