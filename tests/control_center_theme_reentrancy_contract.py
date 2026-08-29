#!/usr/bin/env python3
"""Contract for non-reentrant Control Center theme transactions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "roles/host_desktop_sway/files/privatestack-theme.sh"
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"

theme = THEME.read_text(encoding="utf-8")
manager = MANAGER.read_text(encoding="utf-8")
compile(manager, str(MANAGER), "exec")

assert 'HYPERLAB_THEME_SKIP_CONTROL_CENTER_RELOAD' in theme
assert '[[ ${HYPERLAB_THEME_SKIP_CONTROL_CENTER_RELOAD:-0} != 1 ]]' in theme
assert '/usr/local/bin/privatestack-hyperlab-domains --reload-theme' in theme
assert 'env["HYPERLAB_THEME_SKIP_CONTROL_CENTER_RELOAD"] = "1"' in manager
assert "env=env" in manager
assert 'reload_all = getattr(application, "reload_theme", None)' in manager
assert "reload_all()" in manager
assert "/sys/module/linuwu_sense" not in manager
assert "pkexec" not in manager
assert "sudo " not in manager
assert "shell=True" not in manager

print("Control Center theme re-entrancy contract: OK")
