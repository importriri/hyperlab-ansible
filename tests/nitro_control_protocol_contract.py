#!/usr/bin/env python3
"""Exact-field contract for the privileged Nitro JSON protocol."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "roles/nitro_sense/files/hyperlab-nitro-control-daemon.py"

spec = importlib.util.spec_from_file_location("hyperlab_nitro_control_daemon", DAEMON)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

Broker = module.Broker
ProtocolError = module.ProtocolError

valid = (
    ({"op": "status"}, "status"),
    ({"op": "set_fan", "cpu": 100, "gpu": 100}, "set_fan"),
    ({"op": "set_battery_limiter", "enabled": True}, "set_battery_limiter"),
    (
        {
            "op": "set_rgb",
            "zones": ["ff0000", "00ff00", "0000ff", "ff00ff"],
            "brightness": 100,
        },
        "set_rgb",
    ),
)

for request, expected in valid:
    assert Broker._operation(request) == expected

invalid = (
    {"op": "status", "path": "/etc/shadow"},
    {"op": "set_fan", "cpu": 100, "gpu": 100, "mode": "manual"},
    {"op": "set_fan", "cpu": 100},
    {"op": "set_battery_limiter", "enabled": True, "persist": True},
    {
        "op": "set_rgb",
        "zones": ["ff0000", "00ff00", "0000ff", "ff00ff"],
        "brightness": 100,
        "effect": "static",
    },
    {"op": ["status"]},
)

for request in invalid:
    try:
        Broker._operation(request)
    except ProtocolError:
        pass
    else:
        raise AssertionError(f"request shape was accepted: {request!r}")

print("Nitro broker exact-field protocol contract: OK")
