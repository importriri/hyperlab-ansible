#!/usr/bin/env python3
"""Execute rendered guest configuration; physical rendering is a separate gate."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
GUEST = ROOT / 'roles/guest_desktop_hyprland'
LUA = r'''
package.preload.theme = function() return {} end
local configs, bindings, starts, monitors, rules = {}, {}, {}, {}, {}
local function action(name)
    return function(value) return {kind = name, value = value} end
end
hl = {
    config = function(value) configs[#configs + 1] = value end,
    bind = function(key, value)
        assert(bindings[key] == nil, "duplicate binding: " .. key)
        bindings[key] = value
    end,
    monitor = function(value) monitors[#monitors + 1] = value end,
    on = function(event, callback)
        assert(event == "hyprland.start")
        callback() -- Record startup commands; never execute them.
    end,
    exec_cmd = function(cmd) starts[#starts + 1] = cmd end,
    env = function() end,
    curve = function() end,
    animation = function() end,
    window_rule = function(value) rules[#rules + 1] = value end,
    dsp = {
        exec_cmd = action("exec"), focus = action("focus"), layout = action("layout"),
        window = {
            close = action("close"), fullscreen = action("fullscreen"),
            float = action("float"), pseudo = action("pseudo"), move = action("move"),
            drag = action("drag"), resize = action("resize"),
        },
    },
}
@@CONFIG@@
assert(#configs == 1 and configs[1].general.allow_tearing == false,
       "guest compositor must explicitly disallow tearing")
local full = bindings["ALT + F"]
assert(full and full.kind == "fullscreen", "ALT+F must use native fullscreen")
assert(full.value.mode == "fullscreen" and full.value.action == "toggle",
       "maximization is not fullscreen")
assert(bindings["SUPER + F"] == nil, "guest stole host fullscreen namespace")
for key in pairs(bindings) do
    assert(not key:find("F11", 1, true) and key ~= "CTRL + F",
           "rejected fullscreen shortcut returned")
end
local bars = 0
for _, cmd in ipairs(starts) do
    -- The Workspace Shell entry point falls back to Waybar on its own.
    if cmd == "waybar" or cmd == "hyperlab-workspace session" then bars = bars + 1 end
    assert(not cmd:match("kill.*waybar"), "fullscreen must not kill the bar")
end
assert(bars == 1, "normal guest desktop must launch exactly one bar")
local suppressed = false
for _, rule in ipairs(rules) do
    assert(rule.immediate ~= true, "unreviewed immediate presentation rule")
    if rule.suppress_event == "maximize" and rule.match and rule.match.class == ".*" then
        suppressed = true
    end
end
assert(suppressed, "maximize requests must be suppressed so new windows tile")
assert(#monitors == 1)
@@MONITOR_ASSERT@@
'''


def check(source: str, bar: dict, headless: bool, shell: str = 'quickshell') -> None:
    assert bar['layer'] == 'top', 'guest bar must not become an overlay'
    assert bar.get('exclusive', True) is True, 'ordinary windows must reserve bar space'
    assert bar.get('mode', 'dock') == 'dock', 'normal desktop bar must remain visible'
    defaults = yaml.safe_load((GUEST / 'defaults/main.yml').read_text())
    defaults['guest_desktop_hyprland_headless_monitor'] = headless
    defaults['guest_desktop_hyprland_shell'] = shell
    rendered = Environment(undefined=StrictUndefined).from_string(source).render(**defaults)
    monitor_assert = (
        'assert(monitors[1].output == "HEADLESS-0" and '
        'monitors[1].mode == "1920x1080@144" and monitors[1].scale == 1)'
        if headless else 'assert(monitors[1].output == "" and monitors[1].mode == "preferred")'
    )
    program = LUA.replace('@@CONFIG@@', rendered).replace('@@MONITOR_ASSERT@@', monitor_assert)
    lua = shutil.which('lua')
    assert lua, 'Lua interpreter required; do not silently skip the contract'
    with tempfile.TemporaryDirectory(prefix='hyperlab-presentation-') as temporary:
        script = Path(temporary) / 'contract.lua'
        script.write_text(program)
        result = subprocess.run([lua, str(script)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr


def rejected(source: str, bar: dict, label: str, shell: str = 'quickshell') -> None:
    try:
        check(source, bar, True, shell)
    except AssertionError:
        return
    raise AssertionError('regression not detected: ' + label)


def check_no_lock_behind_looking_glass() -> None:
    """A guest reached through Looking Glass never locks itself idle."""
    lua = (ROOT / "roles/guest_desktop_hyprland/templates/hyprland.lua.j2").read_text()
    guarded = lua.split("{% if not guest_desktop_hyprland_headless_monitor %}", 1)
    assert len(guarded) == 2, "hypridle is not guarded by the headless monitor policy"
    assert 'hl.exec_cmd("hypridle")' in guarded[1].split("{% endif %}", 1)[0]
    assert lua.count('hl.exec_cmd("hypridle")') == 1, "hypridle starts outside the guard"
    idle = (ROOT / "roles/guest_desktop_hyprland/files/hypridle.conf").read_text()
    assert "hyprctl dispatch" not in idle, "hyprctl dispatch takes Lua under the guest configuration"


def main() -> None:
    source = (GUEST / 'templates/hyprland.lua.j2').read_text()
    bar = json.loads((GUEST / 'files/waybar.jsonc').read_text())
    for headless in (False, True):
        for shell in ('quickshell', 'waybar'):
            check(source, bar, headless, shell)
    rejected(source.replace('mode = "fullscreen"', 'mode = "maximized"'), bar, 'maximize')
    old_dispatch = re.sub(
        r'hl\.dsp\.window\.fullscreen\(\{.*?\}\)',
        'hl.dsp.exec_cmd("hyprctl dispatch fullscreen 1")', source, flags=re.S,
    )
    assert old_dispatch != source
    rejected(old_dispatch, bar, 'historical guest shortcut')
    rejected(source.replace('suppress_event = "maximize"', ''), bar, 'maximize requests honoured')
    rejected(source.replace('allow_tearing = false', 'allow_tearing = true'), bar, 'tearing')
    rejected(source.replace('allow_tearing = false,', ''), bar, 'implicit tearing policy')
    rejected(source, dict(bar, layer='overlay'), 'overlay bar')
    rejected(source, dict(bar, exclusive=False), 'lost work area')
    rejected(source.replace('hl.exec_cmd("waybar")', ''), bar, 'disabled bar', 'waybar')
    rejected(source.replace('hl.exec_cmd("hyperlab-workspace session")', ''), bar, 'disabled shell')
    rejected(source.replace('{% else %}\n    hl.exec_cmd("waybar")', '\n    hl.exec_cmd("waybar")'),
             bar, 'two bars')
    check_no_lock_behind_looking_glass()

    host = (ROOT / 'roles/host_desktop_hyprland/templates/hyprland.lua.j2').read_text()
    host = re.sub(r'--[^\n]*', '', host)
    assert re.findall(r'allow_tearing\s*=\s*(\w+)', host) == ['false']
    assert not re.search(r'immediate\s*=\s*true', host)
    assert 'mode = "fullscreen"' in host and 'local main_mod = "SUPER"' in host

    role = ROOT / 'roles/guest_looking_glass_linux'
    defaults = yaml.safe_load((role / 'defaults/main.yml').read_text())
    patch = (role / 'files/pipewire-thread-loop-runtime.patch').read_bytes()
    assert hashlib.sha256(patch).hexdigest() == defaults['guest_looking_glass_linux_runtime_patch_sha256']
    added = '\n'.join(line[1:] for line in patch.decode().splitlines()
                      if line.startswith('+') and not line.startswith('+++'))
    for invariant in ('info.format == SPA_VIDEO_FORMAT_xBGR_210LE',
                      'info.format == SPA_VIDEO_FORMAT_RGBA_F16', 'this->hdrPQ  = this->hdr;',
                      'pw_thread_loop_lock(this->threadLoop)',
                      'pw_thread_loop_unlock(this->threadLoop)'):
        assert invariant in added, invariant
    assert 'this->hdr    = info.format &' not in added
    assert defaults['guest_looking_glass_linux_capture_output'] == 'HEADLESS-0'
    assert defaults['guest_looking_glass_linux_capture_max_fps'] == 144
    client = yaml.safe_load((ROOT / 'roles/looking_glass/defaults/main.yml').read_text())
    assert client['looking_glass_escape_key'] == 'KEY_RIGHTCTRL'
    tasks = (GUEST / 'tasks/main.yml').read_text()
    assert 'src: hyprland.lua.j2' in tasks
    assert '{ src: waybar.jsonc, dest: waybar/config.jsonc }' in tasks
    print('WAYBAR_FULLSCREEN_CONTRACT=PASS')
    print('TEARING_PRESENTATION_CONTRACT=PASS (policy only; physical localization is documented separately)')
    print('LOOKING_GLASS_SDR_REGRESSION=PASS')


if __name__ == '__main__':
    main()
