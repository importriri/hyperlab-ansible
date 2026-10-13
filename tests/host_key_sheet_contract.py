#!/usr/bin/env python3
"""The host key sheet lists every host binding and promises no other.

HostKeys.qml carries the sheet as JSON between markers; the host Hyprland
configuration carries the bindings. Both directions are checked, and the
sheet is opened offscreen in the real launcher (HYPERLAB_RENDER_OUT=<dir>
saves a capture).
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import host_quickshell_runtime_contract as runtime

ROOT = Path(__file__).resolve().parents[1]
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
    for chord in ("SUPER+SHIFT+V", "SUPER+F1", "Right CTRL"):
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
