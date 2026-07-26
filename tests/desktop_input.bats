#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"
}

@test "Foot configuration uses parse-clean 1.26 colour syntax" {
  run python - "${REPO_ROOT}/roles/desktop/files/foot.ini" <<'PY'
from pathlib import Path
import re
import sys

text = Path(sys.argv[1]).read_text()
sections = re.findall(r"(?m)^\[([^]]+)\]$", text)
assert "colors-dark" in sections
assert "colors" not in sections
assert "cursor" not in sections
assert re.search(r"(?m)^cursor=\S+\s+\S+$", text)
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
hardware = yaml.safe_load((root / "group_vars/all/hardware.yml").read_text())["hardware_profiles"]
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
assert "xkb_layout it" in fallback
assert "xkb_variant" not in fallback
assert "xkb_options" not in fallback
for line in ("dwt enabled", "middle_emulation enabled", "natural_scroll enabled", "tap enabled"):
    assert line in fallback

optional = copy.deepcopy(defaults)
optional["keyboard_variant"] = "nodeadkeys"
optional["keyboard_options"] = "ctrl:nocaps"
optional_render = render(optional)
assert "xkb_variant nodeadkeys" in optional_render
assert "xkb_options ctrl:nocaps" in optional_render

for name, profile in hardware.items():
    assert "desktop" in profile, f"{name} has no explicit desktop profile"
    rendered = render(merge(defaults, profile["desktop"]))
    assert f"xkb_layout {profile['desktop']['keyboard_layout']}" in rendered
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
