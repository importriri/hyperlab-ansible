#!/usr/bin/env python
"""Structural contract between the cockpit and the repository it reads.

Discovered by verify.sh and by CI (`tests/*_contract.py`), so the CLI is gated
without a line being added to the workflow - which is the rule that file states
about itself.

Two jobs. It asserts the things that span the two halves of the cockpit and can
only be checked from here, and it runs the component's own suite, so a failure
inside tools/hyperlabctl is a failure of the repository.
"""

import ctypes
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "hyperlabctl"
sys.path.insert(0, str(TOOL))

PASSED = 0
FAILED = 0


# One recording executable, installed under distinct names in a private PATH.
# It never dispatches an unknown request to an installed host program.
PALETTE_STANDIN = r'''
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
config = json.loads((root / "config.json").read_text())
actor = Path(sys.argv[0]).name
args = sys.argv[1:]


def record(kind: str, **values: object) -> None:
    data = (json.dumps(dict(kind=kind, **values)) + "\n").encode()
    fd = os.open(root / "trace.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise RuntimeError("short trace write")
    finally:
        os.close(fd)


def require(condition: bool, message: str) -> None:
    if not condition:
        record("unexpected", actor=actor, argv=args, message=message)
        raise SystemExit(97)


if actor == "cli":
    record("cli", argv=args)
    if args == ["--json", "actions"]:
        print(json.dumps([config["action"]]))
    elif args == config["choices_call"]:
        if config["action"]["target"] == "domain":
            print(json.dumps([{"name": config["target"]}]))
        else:
            print(config["target"])
    elif args == config["resolve"]:
        if config["refuse"] == "text":
            raise SystemExit(4)
        print(config["command"])
    elif args == ["--json"] + config["resolve"]:
        if config["refuse"] == "json":
            raise SystemExit(5)
        print(json.dumps(config["argv"]))
    else:
        require(False, "unexpected CLI request")
elif actor == "rofi":
    offered = sys.stdin.read()
    record("menu", argv=args, offered=offered)
    require(len(args) == 7 and args[:4] == ["-dmenu", "-no-show-icons", "-i", "-p"]
            and args[5:] == ["-theme", str(root / ".config/rofi/rofi-hyperlab.rasi")],
            "unexpected menu options")
    prompt = args[4]
    require(prompt in config["menus"], "unexpected menu prompt")
    response = config["menus"][prompt]
    if response is None:
        raise SystemExit(1)
    print(response)
elif actor in ("json-child", "text-child"):
    record(actor, argv=args)
    raise SystemExit(config["child_rc"] if actor == "json-child" else 0)
elif actor == "foot":
    record("terminal", argv=args)
    if args[0] == "--app-id=hyperlab-panel":
        payload = args[1:]
    else:
        require(args[:2] == ["--app-id=floatterm", "--title=hyperlab: " + config["action"]["id"]],
                "unexpected terminal options")
        payload = args[2:]
    if payload[:2] == [sys.executable, "-c"]:
        require(len(payload) == 4 and json.loads(payload[3]) == config["argv"],
                "unexpected Python positional arguments")
        command = payload
    else:
        require(len(payload) == 5 and payload[:2] == ["bash", "-lc"]
                and payload[3:] == ["_", config["command"]],
                "prepared command is not one positional value")
        command = [str(root / "bin/bash"), "--noprofile", "--norc"] + payload[1:]
    result = subprocess.run(command, input="\n", text=True, capture_output=True, check=False)
    record("terminal-done", rc=result.returncode, stdout=result.stdout, stderr=result.stderr)
    raise SystemExit(result.returncode)
else:
    require(False, "unexpected executable")
'''


def palette_process(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Wait for background terminal completion and reap only this session's children."""
    # Bash exits without waiting for open_panel. Adopt its orphaned descendants
    # so a successful communicate (inherited pipes closed) also permits reaping.
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "get child subreaper")
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "set child subreaper")
    process = None
    completed = False
    try:
        process = subprocess.Popen(
            [env["PATH"] + "/bash", "--noprofile", "--norc", str(script)],
            cwd=script.parent, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        stdout, stderr = process.communicate(timeout=10)
        completed = True
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    finally:
        try:
            if process is not None:
                # Before communicate finishes, the unreaped session leader
                # pins this group to the fixture, even on a pipe timeout.
                if not completed:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=5)
                while True:
                    try:
                        child, _ = os.waitpid(-process.pid, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if child == 0:
                        # A child that closed its pipes can still be alive.
                        # waitpid just proved this group contains our child;
                        # never signal a group after its last child is reaped.
                        os.killpg(process.pid, signal.SIGKILL)
                        os.waitpid(-process.pid, 0)
        finally:
            if process is not None:
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
            if libc.prctl(36, previous.value, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "restore child subreaper")


def palette_case(source: str, name: str, *, action_id: str = "vm.inspect",
                 target_kind: str = "domain", privileged: bool = False,
                 stop: str = "", child_rc: int = 0) -> None:
    """Execute the complete palette; the trace and child argv are the oracle."""
    def require(condition: bool, detail: str) -> None:
        if not condition:
            raise AssertionError("%s: %s" % (name, detail))

    with tempfile.TemporaryDirectory(prefix="hyperlab-palette-") as directory:
        root = Path(directory)
        bindir = root / "bin"
        bindir.mkdir()
        for executable in ("bash", "awk", "cut"):
            installed = shutil.which(executable)
            require(installed is not None, "missing fixture dependency " + executable)
            (bindir / executable).symlink_to(installed)
        for actor in ("cli", "rofi", "foot", "json-child", "text-child"):
            path = bindir / actor
            path.write_text("#!%s\n%s" % (sys.executable, PALETTE_STANDIN))
            path.chmod(0o700)
        # These are literal arguments, independently chosen before execution.
        target = "fixture target 'single' \"double\""
        arguments = [target, "with spaces", "'single quotes'", '"double quotes"',
                     "semi; :", "pipe | :", "*.fixture", "",
                     "$(printf canary > %s/dollar-canary)" % root,
                     "`printf canary > %s/backtick-canary`" % root]
        (root / "expanded.fixture").touch()
        argv = [str(bindir / "json-child")] + arguments
        command = (shlex.join([str(bindir / "text-child"), "text destination"])
                   + ' "$(printf canary > %s/text-canary)"' % root)
        action = {"id": action_id, "label": "Fixture action", "target": target_kind or None,
                  "privileged": privileged, "destructive": False}
        label = ("#" if privileged else " ") + " Fixture action"
        action_line = action_id + "\t" + label + "\n"
        resolve = ["actions", "--resolve", action_id]
        menus = {"hyperlab": action_line.rstrip("\n")}
        choices_call = []
        target_prompt = ""
        if target_kind:
            suffix = {"domain": "domain", "spec": "VM spec", "manifest": "image manifest"}
            target_prompt = action_id + ": " + suffix[target_kind]
            menus[target_prompt] = target
            resolve += ["--" + target_kind, target]
            choices_call = (["--json", "vm", "list"] if target_kind == "domain"
                            else ["actions", "--choices", target_kind])
        if stop in ("action-cancel", "action-empty"):
            menus["hyperlab"] = None if stop == "action-cancel" else ""
        if stop in ("target-cancel", "target-empty"):
            menus[target_prompt] = None if stop == "target-cancel" else ""
        config = {"action": action, "target": target, "resolve": resolve, "menus": menus,
                  "choices_call": choices_call, "command": command, "argv": argv,
                  "refuse": stop, "child_rc": child_rc}
        (root / "config.json").write_text(json.dumps(config))
        # Keep the real main, menu, resolver and execution bodies intact.
        for original, replacement in (
            ("declare -r cli=/usr/local/bin/hyperlabctl",
             "declare -r cli=" + shlex.quote(str(bindir / "cli"))),
            ("declare -r python=/usr/bin/python",
             "declare -r python=" + shlex.quote(sys.executable)),
        ):
            require(source.count(original) == 1, "fixed assignment is missing or duplicated")
            source = source.replace(original, replacement, 1)
        script = root / "palette.sh"
        script.write_text(source)
        # No inherited startup hooks, host CLI, display, credentials or PATH.
        result = palette_process(script, {"PATH": str(bindir), "HOME": str(root),
                                         "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C"})
        trace = [json.loads(line) for line in (root / "trace.jsonl").read_text().splitlines()]
        require(not any(event["kind"] == "unexpected" for event in trace),
                "unexpected fixture invocation: %r" % trace)
        require(not any(event["kind"] == "text-child" for event in trace),
                "textual destination executed: %r" % trace)
        require(not list(root.glob("*-canary")), "shell evaluation created a canary")

        def menu_event(prompt: str, offered: str) -> dict:
            return {"kind": "menu", "argv": ["-dmenu", "-no-show-icons", "-i", "-p", prompt,
                                             "-theme", str(root / ".config/rofi/rofi-hyperlab.rasi")],
                    "offered": offered}

        expected = [{"kind": "cli", "argv": ["--json", "actions"]},
                    menu_event("hyperlab", action_line)]
        if stop not in ("action-cancel", "action-empty"):
            if target_kind:
                expected += [{"kind": "cli", "argv": choices_call},
                             menu_event(target_prompt, target + "\n")]
            if stop not in ("target-cancel", "target-empty"):
                expected.append({"kind": "cli", "argv": resolve})
                if stop != "text" and not privileged:
                    expected.append({"kind": "cli", "argv": ["--json"] + resolve})

        executes = not privileged and not stop
        displays = privileged and not stop
        children = [event for event in trace if event["kind"] == "json-child"]
        if privileged:
            require(not children, "privileged display executed the JSON destination: %r" % trace)
        require(children == ([{"kind": "json-child", "argv": arguments}] if executes else []),
                "exact JSON child receipt differs: %r" % children)
        terminals = [event for event in trace if event["kind"] == "terminal"]
        done = [event for event in trace if event["kind"] == "terminal-done"]
        if executes or displays:
            require(len(terminals) == len(done) == 1, "terminal completion handshake missing")
            request = terminals[0]["argv"]
            options = (["--app-id=hyperlab-panel"] if action_id == "panel.open" else
                       ["--app-id=floatterm", "--title=hyperlab: " + action_id])
            require(request[:len(options)] == options, "wrong terminal options")
            payload = request[len(options):]
            if displays:
                require(len(payload) == 5 and payload[:2] == ["bash", "-lc"]
                        and payload[3:] == ["_", command], "display positional value changed")
                output = ("privileged - review it, then run it yourself:\n\n" + command
                          + "\n\n[press Enter to close] ")
                terminal_rc = 0
            else:
                require(len(payload) == 4 and payload[:2] == [sys.executable, "-c"]
                        and json.loads(payload[3]) == argv, "Python execution request changed")
                output = ("" if action_id == "panel.open" else
                          "\n[exit %d - press Enter to close] " % child_rc)
                terminal_rc = child_rc
            expected.append(terminals[0])
            expected += children
            expected.append({"kind": "terminal-done", "rc": terminal_rc, "stdout": output, "stderr": ""})
        require(trace == expected, "invocation trace differs: expected %r, got %r" % (expected, trace))
        # The child result is checked at receipt/completion, independently of
        # the palette's caller status (its cancellation paths intentionally use 0).
        if child_rc == 0:
            require(result.returncode == 0, "palette failed: %r" % result)
        require(result.stdout == result.stderr == "", "unexpected palette output: %r" % result)


def palette_argv_behavior(source: str) -> None:
    palette_case(source, "ordinary")
    palette_case(source, "ordinary nonzero child", child_rc=23)
    palette_case(source, "panel", action_id="panel.open", target_kind="")
    palette_case(source, "privileged display", action_id="vm.validate", target_kind="spec",
                 privileged=True)
    for stop in ("action-cancel", "action-empty", "text", "json"):
        palette_case(source, stop, stop=stop)
    for target_kind in ("domain", "spec", "manifest"):
        for stop in ("target-cancel", "target-empty"):
            palette_case(source, target_kind + " " + stop, target_kind=target_kind, stop=stop)


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
    else:
        FAILED += 1
        print("  FAIL %s%s" % (name, " -- %s" % detail if detail else ""))


def waybar_config():
    raw = (REPO / "roles/host_desktop_sway/files/waybar.jsonc").read_text()
    return json.loads(re.sub(r"(?m)^\s*//.*$", "", raw))


def contract():
    from hyperlabctl import SCHEMA_VERSION
    from hyperlabctl.commands import REGISTRY as COMMANDS
    from hyperlabctl.operations import WAYBAR_SIGNAL
    from hyperlabctl.providers import REGISTRY as PROVIDERS
    from hyperlabctl.registry import actions
    from hyperlabctl.remedies import REMEDIES

    waybar = waybar_config()
    group = waybar["group/hyperlab"]
    modules = [waybar[name] for name in group["modules"]]

    check("schema version is declared", SCHEMA_VERSION >= 1)
    check("providers were discovered", len(PROVIDERS) >= 6, "%d found" % len(PROVIDERS))
    check("commands were discovered", len(COMMANDS) >= 8, "%d found" % len(COMMANDS))

    # The bar and the CLI must agree, and neither can see the other at runtime.
    signals = {module.get("signal") for module in modules if "signal" in module}
    check("the bar listens on the signal the CLI raises",
          signals == {WAYBAR_SIGNAL}, "bar %s, cli %d" % (signals, WAYBAR_SIGNAL))

    # Every field the bar asks for must be one the CLI can render.
    from hyperlabctl.commands.waybar import FIELDS
    asked = {module["exec"].split()[-1] for module in modules}
    check("every pill asks for a field the CLI knows",
          asked <= set(FIELDS), "bar asks %s" % sorted(asked - set(FIELDS)))

    # Nothing the palette can offer may reference a playbook that is not here.
    for action in actions(repo_root=REPO, include_privileged=True):
        for part in action["command"]:
            if part.startswith("playbooks/"):
                check("offered action %s can actually run" % action["id"],
                      (REPO / part).exists(), "%s is missing" % part)
        if not action["privileged"]:
            check("offered action %s names a real subcommand" % action["id"],
                  action["command"][1] in COMMANDS)

    # An action held back must say what it is waiting for.
    for action in actions(repo_root=REPO, include_unavailable=True):
        if not action["available"]:
            check("held-back action %s names its prerequisite" % action["id"],
                  bool(action["requires"]))

    # Every problem a provider can raise carries its fix.
    declared = set()
    for module in sorted((TOOL / "hyperlabctl" / "providers").glob("*.py")):
        declared |= set(re.findall(r'"id":\s*"([a-z_]+\.[a-z_]+)"', module.read_text()))
    missing = sorted(declared - set(REMEDIES))
    check("every problem id has a remedy", missing == [], "missing %s" % missing)

    # The helper the bar execs must be the one the role deploys.
    tasks = (REPO / "roles/host_desktop_sway/tasks/main.yml").read_text()
    for module in modules:
        binary = module["exec"].split()[0]
        check("the role deploys %s" % binary, Path(binary).name in tasks)

    inspect_checkout = tasks.index("- name: Inspect the configured HyperLab checkout before host writes")
    install_desktop = tasks.index("- name: Install the desktop stack")
    completion = tasks.index("- name: Generate shell completion from the subcommands that exist")
    install_completion = tasks.index("- name: Install the completion, when the CLI could produce one")
    completion_block = tasks[completion:install_completion]
    check("the checkout is refused before package writes", inspect_checkout < install_desktop)
    check("completion runs as the admin user", 'become_user: "{{ admin_user }}"' in completion_block)
    check("completion uses argv rather than a shell command", "argv:" in completion_block and "cmd:" not in completion_block)
    check("the checkout path must be absolute", "host_desktop_sway_hyperlab_checkout is match('^/')" in tasks)

    palette = (REPO / "roles/host_desktop_sway/files/privatestack-hyperlab-palette.sh").read_text()
    check("the palette never evals a resolved command", 'eval "$1"' not in palette)
    check("the palette executes validated JSON argv", '--json "${resolve_args[@]}"' in palette
          and "subprocess.call(argv)" in palette)

    try:
        palette_argv_behavior(palette)
    except Exception as exc:  # noqa: BLE001 - report fixture errors and still run the component suite
        check("palette argv behavior", False, str(exc))
    else:
        check("palette argv behavior", True)
        print("  palette argv behavior: OK")


def component_suite():
    result = subprocess.run([sys.executable, str(TOOL / "tests" / "run.py")],
                            capture_output=True, text=True, check=False,
                            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1",
                                 "HOME": "/nonexistent"})
    tail = (result.stdout or result.stderr).strip().splitlines()
    print("  component suite: %s" % (tail[-1] if tail else "no output"))
    if result.returncode != 0:
        for line in tail:
            if "FAIL" in line:
                print("    %s" % line.strip())
    return result.returncode == 0


def main():
    print("hyperlabctl contract")
    contract()
    ok = component_suite()
    print("  contract: passed %d, failed %d" % (PASSED, FAILED))
    return 0 if (FAILED == 0 and ok) else 1


if __name__ == "__main__":
    sys.exit(main())
