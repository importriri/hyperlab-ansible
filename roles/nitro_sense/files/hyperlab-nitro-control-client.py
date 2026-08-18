#!/usr/bin/env python3
"""Normal-user client for the HyperLab Nitro runtime broker."""
from __future__ import annotations

import argparse
import json
import socket
from typing import Any


SOCKET_PATH = "/run/hyperlab-nitro/control.sock"
MAX_RESPONSE_BYTES = 16384


def request(payload: dict[str, Any]) -> dict[str, Any]:
    wire = (json.dumps(payload, separators=(",", ":")) + "\n").encode()

    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(3.0)
    try:
        conn.connect(SOCKET_PATH)
        conn.sendall(wire)
        chunks = bytearray()
        while len(chunks) <= MAX_RESPONSE_BYTES:
            part = conn.recv(min(2048, MAX_RESPONSE_BYTES + 1 - len(chunks)))
            if not part:
                break
            chunks.extend(part)
            if b"\n" in part:
                break
    finally:
        conn.close()

    if not chunks or len(chunks) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Nitro broker returned an empty or oversized response")

    first_line, _separator, trailing = bytes(chunks).partition(b"\n")
    if trailing.strip():
        raise RuntimeError("Nitro broker returned more than one response")

    response = json.loads(first_line.decode("utf-8"))
    if not isinstance(response, dict) or type(response.get("ok")) is not bool:
        raise RuntimeError("Nitro broker returned an invalid response")
    return response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    fan = sub.add_parser("fan")
    fan.add_argument("cpu", type=int)
    fan.add_argument("gpu", type=int)

    battery = sub.add_parser("battery")
    battery.add_argument("state", choices=("on", "off"))

    rgb = sub.add_parser("rgb")
    rgb.add_argument("brightness", type=int)
    rgb.add_argument("zone1")
    rgb.add_argument("zone2")
    rgb.add_argument("zone3")
    rgb.add_argument("zone4")

    return parser.parse_args()


def payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "status":
        return {"op": "status"}
    if args.command == "fan":
        return {"op": "set_fan", "cpu": args.cpu, "gpu": args.gpu}
    if args.command == "battery":
        return {"op": "set_battery_limiter", "enabled": args.state == "on"}
    if args.command == "rgb":
        return {
            "op": "set_rgb",
            "brightness": args.brightness,
            "zones": [args.zone1, args.zone2, args.zone3, args.zone4],
        }
    raise AssertionError("unreachable command")


def main() -> int:
    try:
        response = request(payload(parse_args()))
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(response, sort_keys=True))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
