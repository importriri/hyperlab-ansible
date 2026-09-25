#!/usr/bin/env python3
"""Behavioural contract for the compositor adapter's shell-facing streams.

Runs the real adapter against inert fake `swaymsg` / `hyprctl` binaries in a
temporary directory. Nothing touches a real compositor, and nothing is
written outside that directory. It proves four things the shell relies on:

  * event watchers re-publish on a heartbeat, so a healthy but quiet stream
    never ages into "stale" and never disables workspace navigation;
  * every workspace snapshot names the focused output, which is how a
    keyboard-summoned launcher, panel or OSD finds its output;
  * an output name that is not a plain connector name is withheld;
  * `shell-window-focus` focuses only the window owned by the calling shell
    process, never a same-titled window from another process;
  * the shared lock helper notifies the shell without waiting for it.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "roles/host_desktop_common/files/privatestack-compositor-adapter.sh"
LOCK = ROOT / "roles/host_desktop_common/files/privatestack-lock.sh"

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def fake_sway(bindir: Path, output: str) -> None:
    write_executable(bindir / "swaymsg", f"""#!/bin/bash
case "$*" in
  *subscribe*) sleep 30 ;;
  *get_workspaces*)
    echo '[{{"num":1,"focused":false,"output":"HDMI-A-1"}},{{"num":2,"focused":true,"output":{output},"urgent":true}}]' ;;
  *get_tree*)
    echo "{{\\"id\\":1,\\"nodes\\":[{{\\"id\\":42,\\"pid\\":$FAKE_OWNER,\\"name\\":\\"HyperLab · Machines\\",\\"nodes\\":[]}},{{\\"id\\":7,\\"pid\\":99999,\\"name\\":\\"HyperLab · guest\\"}}],\\"floating_nodes\\":[]}}" ;;
  *) echo "SWAY $*" ;;
esac
""")


def fake_hyprland(bindir: Path) -> None:
    write_executable(bindir / "hyprctl", """#!/bin/bash
if [[ $1 == clients ]]; then
  echo "[{\\"pid\\":99999,\\"title\\":\\"HyperLab · guest\\",\\"stableId\\":\\"1\\"},{\\"pid\\":$FAKE_OWNER,\\"title\\":\\"HyperLab · Diagnostics\\",\\"stableId\\":\\"18000abc\\"}]"
else
  echo "DISPATCH $*"
fi
""")


def watch_lines(env: dict, seconds: float) -> list[str]:
    process = subprocess.Popen(
        ["bash", str(ADAPTER), "workspace-watch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
    )
    time.sleep(seconds)
    process.terminate()
    try:
        out, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        out, _ = process.communicate()
    return [line for line in out.splitlines() if line.strip()]


def heartbeat_and_output(base_env: dict, bindir: Path) -> None:
    fake_sway(bindir, '"eDP-1"')
    env = dict(base_env, HYPERLAB_COMPOSITOR_BACKEND="sway",
               HYPERLAB_WATCH_HEARTBEAT_SECONDS="1")
    lines = watch_lines(env, 3.5)
    check(len(lines) >= 3,
          "a quiet workspace stream did not re-publish on its heartbeat (%d lines)" % len(lines))
    check(all('"output":"eDP-1"' in line for line in lines),
          "workspace snapshots do not name the focused output: %r" % lines[:1])
    check(all('"active":2' in line and '"urgent":[2]' in line for line in lines),
          "workspace snapshot content changed: %r" % lines[:1])

    fake_sway(bindir, '"eDP-1;rm -rf /"')
    lines = watch_lines(env, 1.2)
    check(bool(lines) and all('"output":""' in line for line in lines),
          "an output name that is not a connector name was passed on: %r" % lines[:1])

    # An out-of-range override falls back to the reviewed interval rather
    # than spinning or disabling the heartbeat.
    fake_sway(bindir, '"eDP-1"')
    env_bad = dict(env, HYPERLAB_WATCH_HEARTBEAT_SECONDS="0")
    lines = watch_lines(env_bad, 1.5)
    check(len(lines) == 1,
          "an invalid heartbeat override changed the interval (%d lines)" % len(lines))


def owner_bound_focus(base_env: dict, bindir: Path, scratch: Path) -> None:
    fake_hyprland(bindir)
    fake_sway(bindir, '"eDP-1"')
    caller = scratch / "caller.sh"
    write_executable(caller, f"""#!/bin/bash
export FAKE_OWNER=$$
HYPERLAB_COMPOSITOR_BACKEND=$1 bash {ADAPTER} shell-window-focus
""")
    for backend, expected, foreign in (
        ("hyprland", 'hl.dsp.focus({ window = "stableid:18000abc" })', "stableid:1 "),
        ("sway", "[con_id=42] focus", "[con_id=7]"),
    ):
        result = subprocess.run(
            ["bash", str(caller), backend],
            capture_output=True, text=True, env=base_env, timeout=20, check=False,
        )
        check(result.returncode == 0,
              "%s: shell-window-focus failed: %s" % (backend, result.stderr.strip()))
        check(expected in result.stdout,
              "%s: the shell-owned workspace window was not focused: %r"
              % (backend, result.stdout))
        check(foreign not in result.stdout,
              "%s: a same-titled window from another process was focused" % backend)

    # Called from a process that owns no workspace window: nothing is focused.
    result = subprocess.run(
        ["bash", str(ADAPTER), "shell-window-focus"],
        capture_output=True, text=True,
        env=dict(base_env, HYPERLAB_COMPOSITOR_BACKEND="sway", FAKE_OWNER="1"),
        timeout=20, check=False,
    )
    check(result.returncode != 0 and "focus" not in result.stdout,
          "shell-window-focus focused something for a process that owns nothing")


def lock_does_not_wait(base_env: dict, bindir: Path, scratch: Path) -> None:
    # A shell that hangs on IPC must not delay the locker.
    write_executable(bindir / "qs", "#!/bin/bash\nsleep 20\n")
    write_executable(bindir / "hyprlock", "#!/bin/bash\necho LOCKED\n")
    write_executable(bindir / "pidof", "#!/bin/bash\nexit 1\n")
    adapter = scratch / "adapter"
    write_executable(adapter, "#!/bin/bash\necho hyprland\n")
    started = time.monotonic()
    result = subprocess.run(
        ["bash", str(LOCK)],
        capture_output=True, text=True, timeout=15, check=False,
        env=dict(base_env, HYPERLAB_COMPOSITOR_ADAPTER=str(adapter)),
    )
    elapsed = time.monotonic() - started
    check("LOCKED" in result.stdout, "the lock helper did not start the locker")
    check(elapsed < 1.5, "the lock helper waited for the shell (%.1fs)" % elapsed)
    source = LOCK.read_text(encoding="utf-8")
    check("ipc call session locking" in source and "timeout 2" in source,
          "the lock helper no longer notifies the shell through the fixed receiver")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hyperlab-adapter-") as scratch_name:
        scratch = Path(scratch_name)
        bindir = scratch / "bin"
        bindir.mkdir()
        base_env = dict(os.environ)
        base_env["PATH"] = str(bindir) + os.pathsep + base_env.get("PATH", "")
        base_env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        base_env.pop("SWAYSOCK", None)

        heartbeat_and_output(base_env, bindir)
        owner_bound_focus(base_env, bindir, scratch)
        lock_does_not_wait(base_env, bindir, scratch)

    if FAILURES:
        for failure in FAILURES:
            print("FAIL:", failure)
        return 1

    print("HyperLab compositor adapter behaviour contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
