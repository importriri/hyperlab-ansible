#!/usr/bin/env python3
"""The host side of the security plane records and detects (ADR 0040).

  1. auditd watches HyperLab's trust points for writes and attribute
     changes under hyperlab-* keys, only paths that exist (a missing one
     stops later rules loading), and the role checks the loaded rules;
  2. the integrity checker, run on a temporary tree, reports nothing on an
     unchanged tree and reports every changed content, mode, link target,
     added and removed file; its baseline is private; without a baseline it
     refuses rather than passing;
  3. the check runs from a hardened oneshot unit every hour, and the role
     records the first baseline once and never accepts a later change by
     itself;
  4. both bricks are in the graph.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "roles/host_integrity/files/hyperlab-integrity.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_audit() -> None:
    defaults = yaml.safe_load((ROOT / "roles/host_audit/defaults/main.yml").read_text())
    watches = defaults["host_audit_watches"]
    require(all(w["key"].startswith("hyperlab-") for w in watches), "an audit key lacks the hyperlab- prefix")
    paths = {w["path"] for w in watches}
    for needed in ("/etc/sudoers", "/etc/sudoers.d", "/etc/gpu-handoff", "/etc/libvirt", "/etc/nftables.d",
                   "/etc/usbguard", "/boot/loader", "/etc/shadow", "/etc/hyperlabctl",
                   "{{ hyperlab_root }}/state", "{{ hyperlab_root }}/bases"):
        require(needed in paths, f"{needed} is not watched")
    template = jinja2.Template((ROOT / "roles/host_audit/templates/50-hyperlab.rules.j2").read_text())
    rendered = template.render(host_audit_present=[{"path": "/etc/sudoers", "key": "hyperlab-privilege"}])
    rules = [line for line in rendered.splitlines() if line and not line.startswith("#")]
    require(rules == ["-w /etc/sudoers -p wa -k hyperlab-privilege"], f"unexpected audit rules: {rules}")
    tasks = (ROOT / "roles/host_audit/tasks/main.yml").read_text()
    require("selectattr('stat.exists')" in tasks, "watches on missing paths would stop the rules loading")
    require("argv: [auditctl, -l]" in tasks and "Require every present trust point watched" in tasks,
            "the loaded rules are not checked")
    require("line: active = yes" in tasks, "audit records do not reach the journal")


def run(tool_env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                          env=tool_env, check=False)


def check_integrity() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        watched = base / "etc"
        (watched / "sudoers.d").mkdir(parents=True)
        (watched / "sudoers").write_text("root ALL=(ALL) ALL\n")
        (watched / "sudoers.d" / "10-wheel").write_text("%wheel ALL=(ALL) ALL\n")
        (watched / "pointer").symlink_to("/srv/checkout-a")
        config = base / "integrity.json"
        config.write_text(json.dumps({"paths": [str(watched), str(base / "absent")]}))
        state = base / "state"
        env = dict(os.environ, HYPERLAB_INTEGRITY_CONFIG=str(config), HYPERLAB_INTEGRITY_STATE=str(state))

        require(run(env, "check").returncode == 2, "a check without a baseline did not refuse")
        require(run(env, "baseline").returncode == 0, "the baseline was not recorded")
        require(stat.S_IMODE((state / "baseline.json").stat().st_mode) == 0o600
                and stat.S_IMODE(state.stat().st_mode) == 0o700, "the baseline is not private")
        clean = run(env, "check")
        require(clean.returncode == 0 and "no difference" in clean.stdout, f"an unchanged tree drifted: {clean.stdout}")

        (watched / "sudoers.d" / "10-wheel").write_text("%wheel ALL=(ALL) NOPASSWD: ALL\n")
        os.chmod(watched / "sudoers", 0o666)
        (watched / "pointer").unlink()
        (watched / "pointer").symlink_to("/srv/checkout-b")
        (watched / "sudoers.d" / "99-new").write_text("sid ALL=(ALL) NOPASSWD: ALL\n")
        drift = run(env, "check")
        out = drift.stdout
        require(drift.returncode == 1, "a changed tree passed")
        for expected in (f"changed  {watched}/sudoers.d/10-wheel (sha256)", f"changed  {watched}/sudoers (mode)",
                         f"changed  {watched}/pointer (target)", f"added    {watched}/sudoers.d/99-new"):
            require(expected in out, f"the check did not report: {expected}\n{out}")
        (watched / "sudoers.d" / "99-new").unlink()
        require(f"removed  {watched}/sudoers.d/99-new" not in run(env, "check").stdout,
                "a file absent from the baseline was reported removed")
        require(run(env, "accept").returncode == 0 and run(env, "check").returncode == 0,
                "an accepted change still drifted")
        (watched / "sudoers").unlink()
        require(f"removed  {watched}/sudoers" in run(env, "check").stdout, "a removed file was not reported")

        config.write_text(json.dumps({"paths": ["relative/path"]}))
        require(run(env, "check").returncode == 2, "a relative path was accepted")


def check_units_and_role() -> None:
    defaults = yaml.safe_load((ROOT / "roles/host_integrity/defaults/main.yml").read_text())
    service = jinja2.Template((ROOT / "roles/host_integrity/templates/hyperlab-integrity.service.j2").read_text()).render(
        **defaults)
    for needle in ("Type=oneshot", "ExecStart=/usr/local/bin/hyperlab-integrity check", "ProtectSystem=strict",
                   "NoNewPrivileges=true", "ReadWritePaths=/var/lib/hyperlab-integrity"):
        require(needle in service, f"the check unit lacks {needle}")
    timer = jinja2.Template((ROOT / "roles/host_integrity/templates/hyperlab-integrity.timer.j2").read_text()).render(
        **defaults)
    require("OnCalendar=hourly" in timer and "Persistent=true" in timer, "the check does not run every hour")
    tasks = (ROOT / "roles/host_integrity/tasks/main.yml").read_text()
    require('creates: "{{ host_integrity_state }}/baseline.json"' in tasks,
            "the role could overwrite a baseline")
    require("accept" not in [line.strip() for line in tasks.splitlines() if line.strip().startswith("argv")],
            "the role accepts changes by itself")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    for brick in ("host_audit", "host_integrity"):
        require(bricks["brick_requires"][brick] == ["base"]
                and bricks["brick_playbooks"][brick] == "playbooks/host-security-plane.yml",
                f"{brick} is not in the brick graph")


def main() -> int:
    check_audit()
    check_integrity()
    check_units_and_role()
    print("Host security plane contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
