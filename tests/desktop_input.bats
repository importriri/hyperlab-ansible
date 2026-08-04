#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"
}

@test "Foot and every palette fragment use parse-clean 1.26 colour syntax" {
  run python - "${REPO_ROOT}" <<'PY'
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
main = (root / "roles/desktop/files/foot.ini").read_text()
assert re.search(r"(?m)^include=~/.config/hyperlab/palette-foot\.ini$", main)
assert "[colors]" not in main
assert "[cursor]" not in main

fragments = sorted((root / "roles/desktop/files/palette").glob("*/hyperlab-palette-foot.ini"))
assert len(fragments) >= 2
for path in fragments:
    text = path.read_text()
    sections = re.findall(r"(?m)^\[([^]]+)\]$", text)
    assert sections == ["colors-dark"], (path, sections)
    assert "[colors]" not in text
    assert "[cursor]" not in text
    assert re.search(r"(?m)^alpha=0\.[0-9]+$", text), path
    assert re.search(r"(?m)^cursor=\S+\s+\S+$", text), path
PY
  [ "$status" -eq 0 ]
}

@test "Sway loads only the rendered per-machine input file" {
  run python - "${REPO_ROOT}/roles/desktop/files/sway.config" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
assert "include input.conf" in text
assert "input type:touchpad" not in text
PY
  [ "$status" -eq 0 ]
}

@test "Input template renders fallback, optional values and both laptop profiles" {
  run python - "${REPO_ROOT}" <<'PY'
from pathlib import Path
import copy
import sys

import yaml
from jinja2 import Environment, StrictUndefined

root = Path(sys.argv[1])
defaults = yaml.safe_load((root / "roles/desktop/defaults/main.yml").read_text())["desktop_input_defaults"]
hardware = yaml.safe_load((root / "group_vars/all/hardware.yml").read_text())["host_profiles"]
template = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True).from_string(
    (root / "roles/desktop/templates/sway-input.conf.j2").read_text()
)

def merge(base, overlay):
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result

def render(data):
    return template.render(desktop_input=data)

fallback = render(defaults)
assert "xkb_layout it,us,ara" in fallback
assert "xkb_variant" not in fallback
assert "xkb_options" not in fallback
for line in ("dwt enabled", "middle_emulation enabled", "natural_scroll enabled", "tap enabled"):
    assert line in fallback

optional = copy.deepcopy(defaults)
optional["keyboard_variant"] = "nodeadkeys"
optional["keyboard_options"] = "ctrl:nocaps"
optional_render = render(optional)
assert "xkb_variant nodeadkeys,," in optional_render
assert "xkb_options ctrl:nocaps" in optional_render

for name, profile in hardware.items():
    assert "desktop" in profile, f"{name} has no explicit desktop profile"
    rendered = render(merge(defaults, profile["desktop"]))
    assert "xkb_layout it,us,ara" in rendered
PY
  [ "$status" -eq 0 ]
}

@test "A misspelled Jinja variable is rejected during rendering" {
  run python - "${REPO_ROOT}" <<'PY'
from pathlib import Path
import sys

import yaml
from jinja2 import Environment, StrictUndefined, UndefinedError

root = Path(sys.argv[1])
defaults = yaml.safe_load((root / "roles/desktop/defaults/main.yml").read_text())["desktop_input_defaults"]
text = (root / "roles/desktop/templates/sway-input.conf.j2").read_text().replace(
    "desktop_input.keyboard_layout", "desktop_input.keyboard_layot", 1
)
template = Environment(undefined=StrictUndefined).from_string(text)
try:
    template.render(desktop_input=defaults)
except UndefinedError:
    raise SystemExit(0)
raise SystemExit("mutation unexpectedly rendered")
PY
  [ "$status" -eq 0 ]
}
