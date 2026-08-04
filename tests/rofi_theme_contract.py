#!/usr/bin/env python3
"""Pin the known-good Rofi/Sway cockpit behaviour found on the Nitro."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "roles" / "desktop" / "files"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


config = (FILES / "rofi-config.rasi").read_text(encoding="utf-8")
launcher = (FILES / "rofi-launcher.rasi").read_text(encoding="utf-8")
hyperlab = (FILES / "rofi-hyperlab.rasi").read_text(encoding="utf-8")
mocha = (FILES / "rofi-mocha.rasi").read_text(encoding="utf-8")
green = (FILES / "palette/green/hyperlab-palette.rasi").read_text(encoding="utf-8")
sway = (FILES / "sway.config").read_text(encoding="utf-8")

require('set $menu rofi -show drun' in sway, "Mod+D launcher command drifted")
require('bindsym $mod+d exec $menu' in sway, "Mod+D binding is missing")
require('bindsym $mod+F1 exec $hyperpalette' in sway, "Mod+F1 binding is missing")

require('hover-select:        false;' in config, "Rofi mouse hover must not steal selection")
require('hover-select:        true;' not in config, "Rofi hover-select regression returned")
require('me-select-entry:' not in config, "Rofi mouse selection override returned")
require('me-accept-entry:' not in config, "Rofi mouse accept override returned")
require(config.count('@theme "rofi-launcher.rasi"') == 1, "launcher must replace the default theme")
require('@import "rofi-launcher.rasi"' not in config, "launcher import fallback regression returned")
require('@import "rofi-mocha.rasi"' in launcher, "launcher palette import is missing")
require("accent:      @hl-accent;" in mocha, "launcher accent alias is not palette-primary")
require("accent2:     @hl-accent2;" in mocha, "secondary accent alias is not palette-driven")
require("hl-accent: #7ee787;" in green, "Green primary accent is not green")
require("border-color:     @accent;" in launcher, "Mod+D selection does not use the primary accent")
require("text-color:       @accent;" in launcher, "Mod+D prompt does not use the primary accent")

for name, theme in (("launcher", launcher), ("hyperlab", hyperlab)):
    require('transparency:     "real";' in theme, f"{name} lost real transparency")
    require('background-color: @base;' in theme,
            f"{name} window is disconnected from the selected palette base")
    require('#1e1e2e' not in theme and '#181825' not in theme,
            f"{name} reintroduced a hard-coded Violet/Catppuccin surface")
    require('background-color: transparent;' not in theme,
            f"{name} uses an unresolved bare transparent value")
    require('@transparent' in theme, f"{name} must use the declared transparent colour")

require('@import "rofi-mocha.rasi"' in hyperlab, "Hyperlab palette import is missing")
require('element normal.normal {' in launcher, "launcher normal state is not explicit")
require('element alternate.normal {' in launcher, "launcher alternate state is not explicit")
require('element selected.normal {' in launcher, "launcher selection state is not explicit")
require('element normal.normal {' in hyperlab, "Hyperlab normal state is not explicit")
require('element alternate.normal {' in hyperlab, "Hyperlab alternate state is not explicit")
require('element selected.normal {' in hyperlab, "Hyperlab selection state is not explicit")

for variant in ("blue", "red"):
    require((FILES / f"palette/{variant}/hyperlab-palette.rasi").is_file(),
            f"{variant} Rofi palette missing")

print("rofi theme contract: OK")
