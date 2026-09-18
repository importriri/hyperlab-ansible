#!/usr/bin/env python3

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

MANAGER_PATH = (
    ROOT
    / "roles"
    / "host_desktop_sway"
    / "files"
    / "privatestack-hyperlab-domains.py"
)

CSS_PATH = (
    ROOT
    / "roles"
    / "host_desktop_sway"
    / "files"
    / "hyperlab-gtk.css"
)

MANAGER = MANAGER_PATH.read_text(encoding="utf-8")
CSS = CSS_PATH.read_text(encoding="utf-8")

EMBEDDED_CSS_MATCH = re.search(
    r'CSS = r"""(.*?)"""',
    MANAGER,
    re.S,
)
assert EMBEDDED_CSS_MATCH is not None
EMBEDDED_CSS = EMBEDDED_CSS_MATCH.group(1)


assert "def _nitro_apply_quick_fan(" in MANAGER
assert '"Quiet · 0%"' in MANAGER
assert '"Gaming · 100%"' in MANAGER
assert '"Policy lifecycle"' in MANAGER
assert '"BROKER ONLINE"' in MANAGER

quick_method = MANAGER.split(
    "def _nitro_apply_quick_fan(",
    1,
)[1].split(
    "def _nitro_apply_fans(",
    1,
)[0]

assert '"--scope"' in quick_method
assert '"runtime"' in quick_method
assert "_nitro_scope()" not in quick_method

build = MANAGER.split(
    "def _build_nitro(",
    1,
)[1].split(
    "def _build_diagnostics(",
    1,
)[0]

order = (
    build.index('"Quick mode"'),
    build.index('"Policy lifecycle"'),
    build.index('"Cooling"'),
    build.index('"Battery"'),
    build.rindex("self._nitro_theme_card()"),
)

assert order == tuple(sorted(order))

assert "surface_explicit = False" in MANAGER
assert "surface_explicit = True" in MANAGER
assert 'if section == "nitro" and not surface_explicit:' in MANAGER
assert 'surface = "overlay"' in MANAGER

for selector in (
    ".nitro-quick-card {",
    ".nitro-policy-card {",
    ".nitro-mode-actions {",
    ".nitro-mode-button {",
    ".nitro-mode-state {",
    ".nitro-appearance-card {",
):
    assert EMBEDDED_CSS.count(selector) == 1, (
        "missing embedded Control Center CSS rule: " + selector
    )

for selector in (
    ".nitro-quick-card {",
    ".nitro-policy-card {",
    ".nitro-mode-actions {",
    "button.nitro-mode-button {",
    "button.nitro-mode-button.active {",
    ".nitro-mode-state {",
    ".nitro-appearance-card {",
):
    assert CSS.count(selector) == 1, selector

assert MANAGER_PATH.read_bytes().endswith(b"\n")
assert CSS_PATH.read_bytes().endswith(b"\n")

print("Nitro enterprise Control Center contract: OK")

# Routine Nitro UI must not expose the raw persistence document.
build_nitro = MANAGER.split(
    "def _build_nitro(",
    1,
)[1].split(
    "def _build_activity(",
    1,
)[0]

assert 'str(status.get("persistence") or "unknown")' not in build_nitro
assert '"broker", "online"' in build_nitro
assert '"mode", fan_mode' in build_nitro
assert '"policy", policy_value' in build_nitro
assert '"controls",' in build_nitro

COMPACT_NITRO_INSPECTOR_CONTRACT = True

# Nitro uses a narrower inspector without changing the other Control Center
# sections that rely on the standard 300px detail surface.
assert '.mock-inspect.nitro-inspect {' in MANAGER
assert 'min-width: 240px;' in MANAGER
assert 'if section == "nitro":' in MANAGER
assert 'add_css_class("nitro-inspect")' in MANAGER
assert 'set_size_request(240, -1)' in MANAGER
assert 'remove_css_class("nitro-inspect")' in MANAGER
assert 'set_size_request(300, -1)' in MANAGER

NITRO_INSPECTOR_WIDTH_CONTRACT = True

# Acer NitroSense physical key must enter the reviewed full Control Center
# directly on the Nitro section. Keycode 433 is captured from the real
# AN515-55 through the active Wayland input path.
from pathlib import Path as _NitroPath

_nitro_sway = (
    _NitroPath(__file__).resolve().parents[1]
    / "roles"
    / "host_desktop_sway"
    / "files"
    / "sway.config"
).read_text(encoding="utf-8")

_nitro_physical_route = (
    "bindcode --release 433 exec "
    "/usr/local/bin/privatestack-hyperlab-domains "
    "--surface overlay --section nitro"
)

assert _nitro_sway.count(_nitro_physical_route) == 1

PHYSICAL_NITROSENSE_ROUTE_CONTRACT = True

# The physical NitroSense key is dedicated to the Nitro Control Center.
# Theme cycling remains on the normal Mod+Shift+T desktop shortcut.
_hardware_profile = (
    _NitroPath(__file__).resolve().parents[1]
    / "group_vars"
    / "all"
    / "hardware.yml"
).read_text(encoding="utf-8")

assert 'keysym: XF86Presentation' not in _hardware_profile
assert (
    "NitroSense is reserved for the HyperLab Nitro control surface."
    in _hardware_profile
)

NITROSENSE_DEDICATED_ROUTE_CONTRACT = True
