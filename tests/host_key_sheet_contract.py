#!/usr/bin/env python3
"""The host key sheet lists every host binding and promises no other.

HostKeys.qml carries the sheet as JSON between markers; the host Hyprland
configuration carries the bindings. The rendered production Lua also runs
against recording dispatchers. Both directions are checked, and the sheet
is opened offscreen in the real launcher (HYPERLAB_RENDER_OUT=<dir> saves
a capture).
"""
from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from jinja2 import Environment, StrictUndefined

import host_quickshell_runtime_contract as runtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl import cli  # noqa: E402
SHEET = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab/HostKeys.qml"
HYPRLAND = ROOT / "roles/host_desktop_hyprland/templates/hyprland.lua.j2"

# Keys bound outside SUPER that the sheet names on purpose, and bindings the
# sheet folds into one row.
NOT_COMPOSITOR = {"Right CTRL"}
FOLDED = {
    "SUPER+1 … 9": {"SUPER+<n>"},
    "SUPER+SHIFT+1 … 9": {"SUPER+SHIFT+<n>"},
    "SUPER+H J K L or arrows": {"SUPER+H", "SUPER+J", "SUPER+K", "SUPER+L",
                                "SUPER+left", "SUPER+down", "SUPER+up", "SUPER+right"},
    "SUPER+SHIFT+H J K L or arrows": {"SUPER+SHIFT+H", "SUPER+SHIFT+J", "SUPER+SHIFT+K", "SUPER+SHIFT+L",
                                      "SUPER+SHIFT+left", "SUPER+SHIFT+down", "SUPER+SHIFT+up",
                                      "SUPER+SHIFT+right"},
    "SUPER+drag": {"SUPER+mouse:272", "SUPER+mouse:273"},
}


def fail(message: str) -> None:
    raise SystemExit(f"Host key sheet contract: {message}")


# These fixtures are independent of the role defaults. Dispatchers return
# data only; even a regressed panic binding cannot execute a host command.
LUA_RECORDER = r"""
package.preload.hyperlab_input = function()
    return {
        keyboard_layout = "us", keyboard_variant = "", keyboard_options = "",
        touchpad = { disable_while_typing = true, middle_button_emulation = true,
                     natural_scroll = false, tap_to_click = true },
        theme_cycle_key = "XF86Launch1",
    }
end
package.preload.hyperlab_palette = function()
    return { active_border = "0xff112233", inactive_border = "0xff445566" }
end
os.execute = function() error("host execution forbidden") end
io.popen = function() error("host execution forbidden") end

local function dispatcher(kind)
    return function(value)
        return { kind = kind, command = kind == "exec" and value or "" }
    end
end
local function inert() end
local submap = "global"
local bindings = {}
hl = {
    monitor = inert, env = inert, config = inert, window_rule = inert,
    dsp = {
        exec_cmd = dispatcher("exec"), focus = dispatcher("focus"),
        submap = dispatcher("submap"),
        window = {
            close = dispatcher("close"), fullscreen = dispatcher("fullscreen"),
            float = dispatcher("float"), move = dispatcher("move"),
            drag = dispatcher("drag"), resize = dispatcher("resize"),
        },
    },
    bind = function(chord, action)
        assert(type(chord) == "string" and type(action) == "table")
        table.insert(bindings, {submap, chord, action.kind, action.command})
    end,
    define_submap = function(name, callback)
        local previous = submap
        submap = name
        callback()
        submap = previous
    end,
}
dofile(arg[1])
local function hex(value)
    assert(type(value) == "string")
    return (value:gsub(".", function(byte)
        return string.format("%02x", string.byte(byte))
    end))
end
for _, binding in ipairs(bindings) do
    io.write(hex(binding[1]), "\t", hex(binding[2]), "\t",
             hex(binding[3]), "\t", hex(binding[4]), "\n")
end
"""


# A shell runs any later argument as code (-c, -lc, a script); each one is
# parsed again, so quoting cannot hide a command from the check below.
SHELLS = {"sh", "bash", "dash", "zsh", "ksh", "mksh", "busybox"}
OPERATORS = set("();<>|&")
MAX_SHELL_DEPTH = 8


def simple_commands(command: str, depth: int = 0) -> list[list[str]]:
    """Every simple command in a shell line, nested shell payloads included."""
    if depth > MAX_SHELL_DEPTH:
        fail(f"shell payloads nest deeper than {MAX_SHELL_DEPTH}: {command!r}")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        fail(f"exec command is not shell-parseable: {command!r}: {exc}")
    commands: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= OPERATORS:
            commands.append([])
        else:
            commands[-1].append(token)
    commands = [argv for argv in commands if argv]
    nested: list[list[str]] = []
    for argv in commands:
        shell = next((i for i, word in enumerate(argv) if Path(word).name in SHELLS), None)
        if shell is not None:
            for payload in argv[shell + 1:]:
                nested.extend(simple_commands(payload, depth + 1))
    return commands + nested


def hyperlabctl_engages(arguments: list[str]) -> bool:
    """Whether the real hyperlabctl parser reads these arguments as panic engage.

    The arguments go through the same global-option normalization and
    argparse tree as cli.main (--json, --no-color, --repo in any position or
    abbreviation). Nothing runs: only the parsed namespace is inspected. An
    invocation the parser rejects never reaches a command.
    """
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            args = cli.build_parser().parse_args(cli._normalize_global_options(list(arguments)))
    except SystemExit:
        return False
    return args.command == "panic" and args.panic_action == "engage"


def runs_panic_engage(command: str) -> bool:
    return any(Path(word).name == "hyperlabctl" and hyperlabctl_engages(argv[i + 1:])
               for argv in simple_commands(command) for i, word in enumerate(argv))


def check_panic_matcher() -> None:
    """The matcher itself, on spellings the check must and must not catch."""
    for command in (
        "/usr/local/bin/hyperlabctl panic engage",
        "/usr/local/bin/hyperlabctl --json --repo /srv/lab panic engage",
        "hyperlabctl panic --no-color engage --repo=/srv/lab",
        "hyperlabctl --js panic engage",
        "setsid -f hyperlabctl panic engage",
        "sh -c 'true && hyperlabctl --json panic engage; :'",
        "foot bash -lc \"dash -c 'hyperlabctl panic engage'\"",
    ):
        if not runs_panic_engage(command):
            fail(f"the panic matcher missed {command!r}")
    for command in (
        "hyperlabctl panic status",
        "hyperlabctl --json panic restore --confirm",
        "hyperlabctl --repo panic engage",
        "foot --app-id=floatterm bash -lc 'hyperlabctl doctor; read -r _'",
        "echo panic engage",
    ):
        if runs_panic_engage(command):
            fail(f"the panic matcher flagged {command!r}")


def check_executed_bindings() -> None:
    lua = shutil.which("lua")
    if not lua:
        fail("real Lua is required to execute the production configuration")
    source = Environment(undefined=StrictUndefined).from_string(
        HYPRLAND.read_text(encoding="utf-8")
    ).render(host_desktop_hyprland_monitor_scale=1.25)
    with tempfile.TemporaryDirectory(prefix="hyperlab-host-keys-") as directory:
        config = Path(directory) / "hyprland.lua"
        config.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [lua, "-", str(config)], input=LUA_RECORDER,
            capture_output=True, text=True, timeout=10, check=False,
        )
    if result.returncode != 0:
        fail(f"production Lua did not execute: {result.stderr.strip()}")
    bindings: list[tuple[str, ...]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 4:
            fail(f"invalid Lua binding record: {line!r}")
        bindings.append(tuple(bytes.fromhex(field).decode("utf-8") for field in fields))
    for submap, chord, kind, command in bindings:
        if kind == "exec" and runs_panic_engage(command):
            fail(f"production Lua binds panic engage in {submap}: {chord}")
    for chord, command in (
        ("SUPER + Escape", "/usr/local/bin/privatestack-lock"),
        ("SUPER + F1", "/usr/bin/qs -c hyperlab ipc call launcher keys"),
        ("SUPER + SHIFT + V", "/usr/bin/qs -c hyperlab ipc call launcher clipboard"),
    ):
        actions = [(kind, value) for submap, key, kind, value in bindings
                   if submap == "global" and key == chord]
        if actions != [("exec", command)]:
            fail(f"production Lua lost {chord} -> {command}: {actions}")


def sheet_chords() -> list[dict]:
    source = SHEET.read_text(encoding="utf-8")
    try:
        block = source.split("// HOST-KEYS-BEGIN", 1)[1].split("// HOST-KEYS-END", 1)[0]
        groups = json.loads(block.split("readonly property var groups:", 1)[1])
    except (IndexError, json.JSONDecodeError) as exc:
        fail(f"HostKeys.qml groups are not JSON between the markers: {exc}")
    rows = [entry for group in groups for entry in group["keys"]]
    if any(set(entry) != {"keys", "does"} or not entry["does"] for entry in rows):
        fail("every row needs exactly a key and what it does")
    return rows


def bound_chords() -> set[str]:
    source = HYPRLAND.read_text(encoding="utf-8")
    # Keys inside the resize submap belong to SUPER + R.
    source = re.sub(r'hl\.define_submap\("resize".*?\nend\)', "", source, flags=re.DOTALL)
    chords = set()
    for first in re.findall(r"hl\.bind\(\s*\n?\s*([^,\n]+),", source):
        first = first.strip()
        if first.startswith("input."):
            continue  # an optional hardware key, configured per host
        if first == 'main_mod .. " + " .. key':
            chords.add("SUPER+<n>")
            continue
        if first == 'main_mod .. " + SHIFT + " .. key':
            chords.add("SUPER+SHIFT+<n>")
            continue
        text = first.replace('main_mod .. "', '"SUPER').strip('"').replace(" + ", "+")
        if text.startswith("XF86"):
            continue  # labelled on the keyboard itself
        chords.add(text)
    return chords


def check_parity() -> None:
    rows = sheet_chords()
    listed = [row["keys"] for row in rows]
    if len(listed) != len(set(listed)):
        fail("a key is listed twice")
    bound = bound_chords()
    covered = set()
    for chord in listed:
        if chord in NOT_COMPOSITOR:
            continue
        expected = FOLDED.get(chord, {chord})
        missing = expected - bound
        if missing:
            fail(f"the sheet promises {chord}, which is not bound: {sorted(missing)}")
        covered |= expected
    unlisted = bound - covered
    if unlisted:
        fail(f"host bindings missing from the sheet: {sorted(unlisted)}")
    for chord in ("SUPER+Escape", "SUPER+SHIFT+V", "SUPER+F1", "Right CTRL"):
        if chord not in listed:
            fail(f"the sheet lost {chord}")
    if any(chord.startswith("ALT+") for chord in listed):
        fail("the host sheet lists guest keys")


def check_directions() -> None:
    # problems/host-arrow-keys-were-never-bound.md: the host bound focus and
    # move to H J K L only, so SUPER+arrows did nothing on the host.
    source = HYPRLAND.read_text(encoding="utf-8")
    bound = {
        (shift, key): (call, direction)
        for shift, key, call, direction in re.findall(
            r'hl\.bind\(\s*main_mod \.\. " \+ (SHIFT \+ )?(\w+)",\s*'
            r'hl\.dsp\.(focus|window\.move)\(\{ direction = "(\w+)" \}\)', source)
    }
    for keys in ("HJKL", ("left", "down", "up", "right")):
        for key, direction in zip(keys, ("left", "down", "up", "right")):
            for shift, call in (("", "focus"), ("SHIFT + ", "window.move")):
                if bound.get((shift, key)) != (call, direction):
                    fail(f"SUPER+{shift.replace(' + ', '+')}{key} is not bound to {call} {direction}")


SCENARIO = """
            sharedSurfaces.openLauncher("", "keys");
            check(launcher.open && launcher.keysMode, "SUPER + F1 did not open the key sheet");
            const keys = launcher.results.filter(row => row.kind === "key");
            check(keys.length >= 20, "the key sheet is not listed");
            check(keys.every(row => row.entry.title !== "SUPER+SHIFT+Escape"
                  && !/emergency|panic/i.test(JSON.stringify(row))),
                  "the real key sheet offered an emergency shortcut");
            for (const chord of ["SUPER+Escape", "SUPER+F1", "SUPER+SHIFT+V"]) {
                check(keys.some(row => row.entry.title === chord),
                      "the real key sheet lost " + chord);
            }
            check(launcher.results.every(row => row.kind === "section" || row.kind === "key"),
                  "the key sheet offered machines or commands");
            launcher.query = "clipboard";
            const found = launcher.results.filter(row => row.kind === "key");
            check(found.length === 1 && found[0].entry.title === "SUPER+SHIFT+V",
                  "searching the sheet does not find the clipboard key");
            launcher.activate(0);
            check(!launcher.open && sharedActions.invoked.length === 0,
                  "a key row ran something");
            sharedSurfaces.openLauncher("", "keys");
"""


def main() -> int:
    check_panic_matcher()
    check_executed_bindings()
    check_parity()
    check_directions()
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    if not runner:
        if os.environ.get("HYPERLAB_REQUIRE_QML_RUNTIME") == "1":
            fail("Qt 6 qmlscene is required")
        print("Host key sheet contract: OK (render SKIPPED, no Qt 6 qmlscene)")
        return 0
    if runtime.OUT:
        Path(runtime.OUT).mkdir(parents=True, exist_ok=True)
    directory = runtime.stage()
    try:
        out = str(Path(runtime.OUT) / "host-keys.png") if runtime.OUT else ""
        source, messages = runtime.scenario_source(1920, 1080, runtime.machines(4), SCENARIO, out=out)
        runtime.run(runner, directory, "host-keys", source, messages)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    print("Host key sheet contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
