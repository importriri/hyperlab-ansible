#!/usr/bin/env python3
"""Structural contract for the narrow Nitro runtime control backend."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/nitro_sense"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


defaults = text(ROLE / "defaults/main.yml")
preflight = text(ROLE / "tasks/preflight.yml")
main = text(ROLE / "tasks/main.yml")
configure = text(ROLE / "tasks/configure.yml")
rollback = text(ROLE / "tasks/rollback.yml")
handlers = text(ROLE / "handlers/main.yml")
tasks = text(ROLE / "tasks/control-backend.yml")
service = text(ROLE / "templates/hyperlab-nitro-control.service.j2")
daemon = text(ROLE / "files/hyperlab-nitro-control-daemon.py")
client = text(ROLE / "files/hyperlab-nitro-control-client.py")

for required in (
    "nitro_sense_control_socket",
    "nitro_sense_control_daemon",
    "nitro_sense_control_client",
    "nitro_sense_control_unit",
    "nitro_sense_control_service",
    "nitro_sense_control_rgb_min_interval_ms",
    "nitro_sense_control_max_request_bytes",
):
    assert required in defaults, required

assert "include_tasks: control-backend.yml" in configure
assert "nitro_sense_use_out_of_tree | bool" in configure

for path_var in (
    "nitro_sense_control_unit",
    "nitro_sense_control_daemon",
    "nitro_sense_control_client",
):
    assert path_var in preflight, path_var
    assert path_var in rollback, path_var

assert "SO_PEERCRED" in daemon
assert "caller-supplied path" in daemon
assert "unsupported operation" in daemon
assert "REQUEST_FIELDS" in daemon
assert '"status": frozenset({"op"})' in daemon
assert '"set_fan": frozenset({"op", "cpu", "gpu"})' in daemon
assert '"set_battery_limiter": frozenset({"op", "enabled"})' in daemon
assert '"set_rgb": frozenset({"op", "zones", "brightness"})' in daemon
assert "invalid request fields" in daemon
assert '"set_fan"' in daemon
assert '"set_battery_limiter"' in daemon
assert '"set_rgb"' in daemon
assert '"effect": False' in daemon
assert "rgb_min_interval" in daemon
assert "O_NOFOLLOW" in daemon

assert "pkexec" not in daemon
assert "subprocess" not in daemon
assert "shell=True" not in daemon

assert 'SOCKET_PATH = "/run/hyperlab-nitro/control.sock"' in client
assert "subprocess" not in client
assert "shell=True" not in client

assert "RestrictAddressFamilies=AF_UNIX" in service
assert "NoNewPrivileges=yes" in service
assert "ProtectSystem=strict" in service
assert "RuntimeDirectory=hyperlab-nitro" in service
assert "IPAddressDeny=any" in service

assert 'become_user: "{{ nitro_sense_control_user }}"' in tasks
assert "status" in tasks
assert "runtime-only" in tasks
assert "Restart Nitro runtime control backend" in handlers

assert "Preview the Nitro runtime control landing in check mode" in main
assert "include_tasks: control-backend.yml" in main
assert "ansible_check_mode" in main
assert tasks.count("when: not ansible_check_mode") >= 5
assert "when: not ansible_check_mode" in handlers

print("nitro control backend contract: OK")
