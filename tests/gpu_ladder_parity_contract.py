#!/usr/bin/env python3
"""Native QML and trust-claim validators agree with the configured CLI ladder."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import shutil

import yaml

import host_quickshell_runtime_contract as runtime
from recovery_gpu_ladder_contract import cli_ladder

ROOT = Path(__file__).resolve().parents[1]


def literal_ladder(path: Path) -> dict[str, int]:
    assignments = [node.value for node in ast.parse(path.read_text()).body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "GPU_LADDER"
                           for target in node.targets)]
    assert len(assignments) == 1, f"{path.name}: missing or duplicate GPU_LADDER"
    value = assignments[0]
    assert isinstance(value, ast.Dict), f"{path.name}: ladder must be a literal mapping"
    keys = [ast.literal_eval(key) for key in value.keys]
    assert len(set(keys)) == len(keys), f"{path.name}: duplicate ladder identity"
    ladder = ast.literal_eval(value)
    assert all(isinstance(key, str) and type(rank) is int for key, rank in ladder.items()), path
    return ladder


def main() -> int:
    levels = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())["gpu_trust_levels"]
    rows = cli_ladder(levels)["cli"]
    expected = {row["name"]: row["level"] for row in rows}
    for path in (ROOT / "tools/hyperlabctl/hyperlabctl/render.py", ROOT / "tools/focus_accent.py"):
        assert literal_ladder(path) == expected, f"{path.name}: GPU_LADDER differs from CLI"

    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    assert runner, "Qt 6 qmlscene is required for native GPU ladder parity"
    body = '''
            const expected = @@EXPECTED@@;
            const actual = Object.keys(sharedState.gpuLadder)
                .map(name => ({name: name, level: sharedState.gpuLadder[name]}))
                .sort((a, b) => b.level - a.level);
            check(JSON.stringify(actual) === JSON.stringify(expected),
                  "ShellState.gpuLadder differs from CLI");
            const component = Qt.createComponent("OwnershipInstrument.qml");
            check(component.status === Component.Ready, "OwnershipInstrument failed to load");
            const instrument = component.createObject(window.contentItem, {
                tokens: sharedTokens, theme: sharedTheme, icons: sharedIcons, shellState: sharedState
            });
            check(instrument !== null, "OwnershipInstrument failed to instantiate");
            const rungs = instrument.rungs.map(row => ({name: row.identity, level: row.rung}));
            check(JSON.stringify(rungs) === JSON.stringify(expected),
                  "OwnershipInstrument.rungs differs from CLI");
            instrument.destroy();
'''.replace("@@EXPECTED@@", json.dumps([{"name": row["name"], "level": row["level"]} for row in rows]))
    directory = runtime.stage()
    try:
        source, messages = runtime.scenario_source(800, 600, [], body)
        runtime.run(runner, directory, "native-gpu-ladder-parity", source, messages)
    finally:
        shutil.rmtree(directory)
    print("GPU ladder parity contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
