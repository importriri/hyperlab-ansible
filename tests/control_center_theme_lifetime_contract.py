#!/usr/bin/env python3
# Contract for Control Center lifetime across internal theme changes.
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
THEME = ROOT / "roles/host_desktop_sway/files/privatestack-theme.sh"
SWAY = ROOT / "roles/host_desktop_sway/files/sway.config"

manager = MANAGER.read_text(encoding="utf-8")
theme = THEME.read_text(encoding="utf-8")
sway = SWAY.read_text(encoding="utf-8")

compile(manager, str(MANAGER), "exec")

assert 'env["HYPERLAB_THEME_SKIP_CONTROL_CENTER_RELOAD"] = "1"' in manager
assert 'env["HYPERLAB_THEME_DEFER_SWAY_RELOAD"] = "1"' in manager
assert "self._theme_sway_reload_pending = False" in manager
assert "self._theme_sway_reload_pending = True" in manager
assert "def _flush_pending_theme_sway_reload(self) -> None:" in manager
assert '["/usr/bin/swaymsg", "-q", "reload"]' in manager
assert "start_new_session=True" in manager

close_start = manager.index("    def close_surface(")
close_end = manager.index("\n    def ", close_start + 1)
close_block = manager[close_start:close_end]
assert "self.set_visible(False)" in close_block
assert "self._flush_pending_theme_sway_reload()" in close_block
assert close_block.index("self.set_visible(False)") < close_block.index(
    "self._flush_pending_theme_sway_reload()"
)

assert "HYPERLAB_THEME_DEFER_SWAY_RELOAD" in theme
assert '[[ ${HYPERLAB_THEME_DEFER_SWAY_RELOAD:-0} != 1 ]]' in theme
assert "swaymsg -q reload" in theme
assert "exec_always /usr/local/bin/privatestack-hyperlab-session" in sway

# The panel itself still owns dismissal through the existing backdrop path.
assert 'lambda *_args: self.close_surface()' in manager
assert "shell=True" not in manager
assert "os.system" not in manager

print("Control Center theme lifetime contract: OK")
