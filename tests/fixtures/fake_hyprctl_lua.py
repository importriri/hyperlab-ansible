#!/usr/bin/env python3
"""hyprctl stand-in for a Hyprland Lua configuration.

`hyprctl dispatch X` evaluates `hl.dispatch(X)`, so X must be a Lua
dispatcher expression. This stand-in runs X through a real Lua interpreter
against a recording `hl.dsp` table: a classic `workspace 11` fails here as
it fails in Hyprland 0.56.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

LUA = r"""
hl = {dsp = {
  focus = function(t) return {kind = "focus", value = t.workspace} end,
  exec_cmd = function(c) return {kind = "exec", value = c} end,
  window = {move = function(t) return {kind = "move", value = t.workspace} end},
}}
local chunk, err = load("return " .. arg[1])
if not chunk then io.stderr:write(err) os.exit(3) end
local ok, r = pcall(chunk)
if not ok or type(r) ~= "table" then io.stderr:write(tostring(r)) os.exit(3) end
io.write(r.kind, "\n", tostring(r.value))
"""

state_path = os.environ["FAKE_HYPR_STATE"]
log_path = os.environ["FAKE_HYPR_LOG"]
state = json.loads(Path(state_path).read_text())
args = sys.argv[1:]


def log(entry):
    with open(log_path, "a") as handle:
        handle.write(json.dumps(entry) + "\n")


log(args)
if args[:2] == ["-j", "activeworkspace"]:
    print(json.dumps({"id": state["active"]}))
elif args[:2] == ["-j", "workspaces"]:
    print(json.dumps([{"id": int(k), "windows": v} for k, v in state["windows"].items()]))
elif args[:1] == ["dispatch"] and len(args) == 2:
    result = subprocess.run(
        ["lua", "-", args[1]], input=LUA, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print("error: " + result.stderr.strip())
        sys.exit(0)
    kind, value = result.stdout.split("\n", 1)
    if kind in ("focus", "move"):
        state["active"] = int(value)
    log([kind, value])
    print("ok")
else:
    print("unknown request", file=sys.stderr)
    sys.exit(3)
Path(state_path).write_text(json.dumps(state))
