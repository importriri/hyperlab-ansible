#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAEMON = (
    ROOT
    / "roles/nitro_sense/files"
    / "hyperlab-nitro-control-daemon.py"
)

spec = importlib.util.spec_from_file_location(
    "nitro_daemon",
    DAEMON,
)

assert spec is not None
assert spec.loader is not None

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FakeSysfsBroker(module.Broker):
    @staticmethod
    def _write_verify(path: Path, desired: str) -> str:
        # A regular tempfile must emulate sysfs replacement semantics.
        # O_WRONLY on an ordinary file would otherwise leave old suffix bytes.
        path.write_text(desired + "\n", encoding="utf-8")
        observed = path.read_text(encoding="utf-8").strip()

        if observed != desired:
            raise module.ProtocolError(
                f"fake sysfs refused {desired}: observed {observed}"
            )

        return observed


Broker = FakeSysfsBroker


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    fan = root / "fan"
    battery = root / "battery"
    rgb = root / "rgb"

    fan.write_text("100,100\n")
    battery.write_text("1\n")
    rgb.write_text("ffffff,ffffff,ffffff,ffffff,25\n")

    state_dir = root / "state"
    state_dir.mkdir(mode=0o700)

    state = state_dir / "persistent.json"

    args = argparse.Namespace(
        socket=str(root / "sock"),
        user=getpass.getuser(),
        model="Nitro AN515-55",
        fan_path=str(fan),
        battery_path=str(battery),
        rgb_path=str(rgb),
        state_path=str(state),
        baseline_fan="100,100",
        baseline_battery="1",
        baseline_rgb="ffffff,ffffff,ffffff,ffffff,25",
        baseline_rgb_managed=True,
        per_zone_enabled=True,
        rgb_min_interval_ms=0,
        max_request_bytes=4096,
    )

    broker = Broker(args)

    status = broker.dispatch({"op": "status"})["status"]

    assert status["persistence"]["scope_default"] == "runtime"
    assert status["persistence"]["overrides"] == []

    broker.dispatch(
        {
            "op": "set_fan",
            "cpu": 90,
            "gpu": 91,
            "scope": "runtime",
        }
    )

    assert not state.exists()
    assert fan.read_text().strip() == "90,91"

    broker.dispatch(
        {
            "op": "set_fan",
            "cpu": 92,
            "gpu": 93,
            "scope": "persistent",
        }
    )

    assert fan.read_text().strip() == "92,93"

    saved = json.loads(state.read_text())

    assert saved["fan"] == "92,93"

    broker.dispatch(
        {
            "op": "set_fan",
            "cpu": 94,
            "gpu": 95,
            "scope": "runtime",
        }
    )

    status = broker.dispatch({"op": "status"})["status"]

    assert status["runtime"]["fan"] == "94,95"
    assert status["persistence"]["saved"]["fan"] == "92,93"

    broker.dispatch(
        {
            "op": "clear_persistent",
            "target": "all",
        }
    )

    status = broker.dispatch({"op": "status"})["status"]

    assert status["persistence"]["overrides"] == []
    assert fan.read_text().strip() == "100,100"
    assert battery.read_text().strip() == "1"
    assert (
        rgb.read_text().strip()
        == "ffffff,ffffff,ffffff,ffffff,25"
    )
    assert status["runtime"]["fan"] == "100,100"
    assert status["runtime"]["battery_limiter"] is True
    assert (
        status["runtime"]["per_zone"]
        == "ffffff,ffffff,ffffff,ffffff,25"
    )

    # If Ansible does not own RGB, clearing persistent state must not
    # synthesize a colour write. Fan and battery still return to their
    # concrete Ansible-managed baseline.
    fan.write_text("33,34\n")
    battery.write_text("0\n")
    rgb.write_text("123456,234567,345678,456789,77\n")

    state.write_text(
        '{"version":1,'
        '"fan":"70,71",'
        '"battery_limiter":false,'
        '"per_zone":"abcdef,bcdefa,cdefab,defabc,88"}\n'
    )
    state.chmod(0o600)

    unmanaged_args = argparse.Namespace(**vars(args))
    unmanaged_args.baseline_rgb_managed = False
    unmanaged_broker = broker.__class__(unmanaged_args)

    unmanaged_broker.dispatch(
        {
            "op": "clear_persistent",
            "target": "all",
        }
    )

    unmanaged_status = unmanaged_broker.dispatch(
        {"op": "status"}
    )["status"]

    assert unmanaged_status["persistence"]["overrides"] == []
    assert fan.read_text().strip() == "100,100"
    assert battery.read_text().strip() == "1"
    assert (
        rgb.read_text().strip()
        == "123456,234567,345678,456789,77"
    )
    assert unmanaged_status["runtime"]["fan"] == "100,100"
    assert unmanaged_status["runtime"]["battery_limiter"] is True
    assert (
        unmanaged_status["runtime"]["per_zone"]
        == "123456,234567,345678,456789,77"
    )

print("Nitro runtime/persistent contract: OK")
