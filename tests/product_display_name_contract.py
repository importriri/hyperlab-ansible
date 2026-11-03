#!/usr/bin/env python3
"""Verify the shared product name at the presentation boundaries."""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

import host_quickshell_runtime_contract as runtime
import host_compositor_adapter_behaviour_contract as adapter

ROOT = Path(__file__).resolve().parents[1]
QML = runtime.QML
PRODUCT = ROOT / "tools/product.yml"
HISTORY = "The product was called HyperLab before 2026-11."
OLD = re.compile(r"HyperLab|Hyperlab|HYPERLAB")
# Tokenize comments separately: internal component identifiers and input
# parsing regexes are not presentation strings. Include nested JS strings.
TOKENS = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`', re.S)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def qml_strings() -> None:
    for path in sorted(QML.glob("*.qml")):
        source = path.read_text(encoding="utf-8")
        for token in TOKENS.finditer(source):
            value = token.group()
            if value.startswith(("//", "/*")):
                continue
            if not value.startswith("`"):
                value = ast.literal_eval(value)
            require(not OLD.search(value), f"{path.name}: old product display string {value}")
            require("Sfere" not in value, f"{path.name}: product name duplicated outside shared input")


def cli_contract() -> str:
    sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))
    from hyperlabctl import __version__, cli

    name = cli.PRODUCT_NAME
    require(name == yaml.safe_load(PRODUCT.read_text())["name"], "CLI/shared name drift")
    parser = cli.build_parser()
    require(parser.prog == "hyperlabctl", "CLI command name changed")
    help_text = parser.format_help()
    require(name in help_text and not OLD.search(help_text), "CLI help uses old product name")
    output = io.StringIO()
    with redirect_stdout(output):
        try:
            parser.parse_args(["--version"])
        except SystemExit as exc:
            require(exc.code == 0, "version failed")
    require(output.getvalue().strip() == f"{name} (hyperlabctl {__version__})", "CLI version banner drift")
    require(not OLD.search(output.getvalue()), "CLI version uses old product name")
    def check_help(current: argparse.ArgumentParser) -> None:
        require(not OLD.search(current.format_help()), "discovered command help uses old product name")
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    check_help(child)
    check_help(parser)
    with tempfile.TemporaryDirectory(prefix="product-input-") as temporary:
        directory = Path(temporary)
        path = directory / "product.yml"
        for raw in ('', '{}', '{"name":"A","name":"B"}', '{"name":null}',
                    '{"name":"Bad\\nname"}', '{"name":"A","other":1}'):
            path.write_text(raw)
            try:
                cli._product_name(path)
            except (OSError, ValueError):
                pass
            else:
                raise AssertionError(f"accepted invalid product input: {raw!r}")
        path.write_text('{"name":"Example Name"}\n')
        require(cli._product_name(path) == "Example Name", "name source cannot change independently")
        path.chmod(0)
        try:
            cli._product_name(path)
        except (OSError, ValueError):
            pass
        else:
            raise AssertionError("accepted unreadable product input")
        path.chmod(0o600)
        redirected = directory / "redirect.yml"
        redirected.symlink_to(path)
        parent = directory / "redirected"
        parent.symlink_to(directory, target_is_directory=True)
        for bad in (redirected, parent / path.name, directory / "missing.yml"):
            try:
                cli._product_name(bad)
            except (OSError, ValueError):
                pass
            else:
                raise AssertionError(f"accepted missing/redirected input: {bad}")
    return name


def deployment_contract() -> None:
    config = yaml.safe_load((ROOT / "group_vars/all/host-desktop.yml").read_text())
    stage = config["host_desktop_common_shell_stage"]
    require(stage["config_root"] == "/etc/xdg/quickshell/hyperlab", "Quickshell config name changed")
    tasks = yaml.safe_load((ROOT / "roles/host_desktop_common/tasks/main.yml").read_text())
    copies = [task["ansible.builtin.copy"] for task in tasks if "ansible.builtin.copy" in task]
    product = [copy for copy in copies if copy.get("src", "").endswith("/tools/product.yml")]
    require(len(product) == 1, "shared product name is not deployed exactly once")
    deployed_source = Path(Environment(undefined=StrictUndefined).from_string(product[0]["src"]).render(
        playbook_dir=str(ROOT / "playbooks")))
    require(deployed_source.resolve() == PRODUCT and deployed_source.read_bytes() == PRODUCT.read_bytes(),
            "deployment does not copy the canonical product input")
    require(product[0]["dest"] == "{{ host_desktop_common_shell_stage.config_root }}/product.yml"
            and product[0]["owner"] == product[0]["group"] == "root"
            and product[0]["mode"] == "0644", "product deployment path/ownership drift")
    shell_source = next(copy for copy in copies if copy.get("src") == "quickshell/hyperlab/")
    require(copies.index(product[0]) < copies.index(shell_source), "product input installed after its consumers")
    for filename, namespace in (("HyperLabBar.qml", "hyperlab-bar"),
                                ("HyperLabDesktop.qml", "hyperlab-desktop")):
        source = (QML / filename).read_text()
        require(re.findall(r'WlrLayershell.namespace:\s*"([^"]+)"', source) == [namespace],
                f"{filename}: internal namespace changed")


def docs_contract(name: str) -> None:
    for filename in ("README.md", "docs/hyperlab-shell.md"):
        source = (ROOT / filename).read_text()
        require(name in source.splitlines()[0], f"{filename}: product heading missing")
        require(source.count(HISTORY) == 1, f"{filename}: history line missing or duplicated")
        # Code identifiers such as HYPERLAB_REQUIRE_QML_RUNTIME keep their
        # spelling; a product word in prose or a diagram does not.
        require(not re.search(r"\b(?:HyperLab|Hyperlab|HYPERLAB)\b", source.replace(HISTORY, "")),
                f"{filename}: old product prose")


def notification_contract(name: str) -> None:
    """Execute the real notification functions with recording executables."""
    with tempfile.TemporaryDirectory(prefix="product-notify-") as temporary:
        directory = Path(temporary)
        recorder = directory / "notify-send"
        recorder.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        recorder.chmod(0o755)
        command = directory / "hyperlabctl"
        command.write_text(f'#!/bin/sh\nprintf \'%s\\n\' \'{name} (hyperlabctl fixture)\'\n')
        command.chmod(0o755)
        for filename, function, call in (
            ("privatestack-theme.sh", "notify", 'notify "Theme changed"'),
            ("privatestack-keyboard.sh", "notify_layout", 'notify_layout "us"'),
            ("privatestack-waybar.sh", "notify_bar_failure", 'notify_bar_failure'),
        ):
            source = (ROOT / "roles/host_desktop_sway/files" / filename).read_text()
            lexer = shlex.shlex(source.replace("\\\n", ""), posix=True, punctuation_chars=";&|()\n")
            lexer.whitespace = " \t\r"
            commands: list[list[str]] = [[]]
            for token in lexer:
                if any(char in token for char in ";&|()\n") and set(token) <= set(";&|()\n"):
                    commands.append([])
                else:
                    commands[-1].append(token)
            for command_tokens in commands:
                if "notify-send" not in command_tokens:
                    continue
                position = command_tokens.index("notify-send")
                if position and command_tokens[position - 1] == "-v":
                    continue
                require(not any(OLD.search(token) for token in command_tokens[position + 1:]),
                        f"{filename}: old notification product string")
            # Bash functions are complete top-level blocks; source only the
            # notification function, never the runtime controller around it.
            match = re.search(r"^" + function + r"\(\) \{\n.*?^\}", source, re.M | re.S)
            require(match is not None, f"{filename}: notification function missing")
            result = subprocess.run(["bash", "-c", match[0] + "\n" + call],
                                    capture_output=True, text=True, check=False,
                                    env={**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"]})
            require(result.returncode == 0, f"{filename}: notification failed: {result.stderr}")
            argv = json.loads(result.stdout)
            require(argv[argv.index("--app-name") + 1] == name, f"{filename}: wrong notification app name")
            require(not any(OLD.search(value) for value in argv), f"{filename}: old notification text")
            for failure in ("exit 1", "printf '%s\\n' invalid"):
                command.write_text('#!/bin/sh\n' + failure + '\n')
                refused = subprocess.run(["bash", "-c", match[0] + "\n" + call],
                                         capture_output=True, text=True, check=False,
                                         env={**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"]})
                require(refused.returncode != 0 and not refused.stdout,
                        f"{filename}: notification defaulted after invalid name read")
            command.write_text(f'#!/bin/sh\nprintf \'%s\\n\' \'{name} (hyperlabctl fixture)\'\n')


SCENARIO = r'''
            const expected = @@NAME@@;
            check(sharedState.productName === expected, "shell/shared name drift");
            check(sharedState.productByline === "by Doppiari", "product byline drift");
            function texts(item) {
                let result = [];
                if (item.text !== undefined) result.push(String(item.text));
                for (const child of item.children || []) result = result.concat(texts(child));
                return result;
            }
            check(texts(rail).includes(expected), "bar does not display shared product name");
            check(texts(desktop).includes(expected), "desktop does not display shared product name");
            check(texts(desktop).includes("by Doppiari"), "desktop byline missing");
            for (const destination of ["machines", "controls", "diagnostics", "workbench", "devices"]) {
                sharedSurfaces.openWorkspace(destination);
                check(workspaceSurface.title.startsWith(expected + " · "), "window title drift");
                check(!texts(workspaceSurface).some(text => /HyperLab|Hyperlab|HYPERLAB/.test(text)),
                      "workspace renders an old product display string");
            }
            check(launcher.hostKeys.productName === expected, "key-sheet name binding missing");
            check(launcher.hostKeys.groups[0].title === expected, "key-sheet product title drift");
            for (const raw of ["", "{}", '{"name":"A","name":"B"}', '{"name":null}',
                               '{"name":"A","other":1}', '{"name":"Bad\\nname"}']) {
                check(sharedState.parseProductName(raw) === "", "shell accepted invalid product input");
            }
            check(sharedState.parseProductName('{"name":"Example Name"}') === "Example Name",
                  "shell cannot consume a changed shared value");
            sharedSurfaces.closeWorkspace();
'''


def shell_contract(name: str) -> None:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    require(runner is not None, "Qt 6 qmlscene required for product presentation")
    directory = runtime.stage()
    try:
        out = os.environ.get("HYPERLAB_RENDER_OUT", "")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
        for width, height in ((1920, 1080), (800, 600)):
            # The narrow bar intentionally collapses the wordmark to the glyph.
            body = SCENARIO.replace("@@NAME@@", json.dumps(name))
            if width < 1000:
                body = body.replace('check(texts(rail).includes(expected), "bar does not display shared product name");', '')
            capture = str(Path(out) / f"product-desktop-{width}.png") if out else ""
            source, messages = runtime.scenario_source(width, height, [], body, out=capture)
            runtime.run(runner, directory, "product-display-" + str(width), source, messages)
            if out:
                capture = str(Path(out) / f"product-bar-{width}.png")
                source, messages = runtime.scenario_source(width, height, [], body, out=capture)
                source = source.replace("window.contentItem.grabToImage", "rail.grabToImage")
                runtime.run(runner, directory, "product-bar-" + str(width), source, messages)
    finally:
        shutil.rmtree(directory)


def native_name_contract(name: str) -> None:
    """Execute the production name binding with the real FileView API only."""
    runner = shutil.which("qs")
    require(runner is not None, "Quickshell required for product file transport")
    source = (QML / "ShellState.qml").read_text()
    # Keep the complete production binding, parser and FileView, excluding
    # every host observation process. Only the file path is substituted.
    source = source.split("    readonly property string statusBridge:", 1)[0]
    require("id: productFile" in source, "product file transport missing")
    with tempfile.TemporaryDirectory(prefix="product-file-") as temporary:
        directory = Path(temporary)
        (directory / "run").mkdir(mode=0o700)
        path = directory / "product.yml"
        scene = source.replace('"/etc/xdg/quickshell/hyperlab/product.yml"', json.dumps(str(path)))
        scene += '''
    Timer {
        interval: 50; running: true
        onTriggered: { console.log("PRODUCT_RESULT=" + JSON.stringify(state.productName)); Qt.quit(); }
    }
}
'''
        (directory / "shell.qml").write_text(scene)
        for raw, expected in ((PRODUCT.read_text(), name), ('{"name":"Example Name"}', "Example Name"),
                              ('{"name":"A","name":"B"}', ""), ("{}", ""), (None, "")):
            if raw is None:
                path.unlink()
            else:
                path.write_text(raw)
            result = subprocess.run([runner, "-p", str(directory), "--no-color"],
                                    capture_output=True, text=True, timeout=10, check=False,
                                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
                                         "QT_QUICK_BACKEND": "software", "QT_FORCE_STDERR_LOGGING": "1",
                                         "WAYLAND_DISPLAY": "", "XDG_RUNTIME_DIR": str(directory / "run"),
                                         "XDG_CACHE_HOME": str(directory / "cache")})
            output = result.stdout + result.stderr
            records = re.findall(r'PRODUCT_RESULT=("[^"\n]*")', output)
            require(result.returncode == 0 and len(records) == 1, f"native product read failed: {output}")
            require(json.loads(records[0]) == expected, f"native product read/default drift: {output}")
            require(not re.search(r"ReferenceError|TypeError|Error loading configuration", output), output)


def focus_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="product-focus-") as temporary:
        directory = Path(temporary)
        bindir = directory / "bin"
        bindir.mkdir()
        env = {**os.environ, "PATH": str(bindir) + ":" + os.environ["PATH"]}
        adapter.FAILURES.clear()
        adapter.owner_bound_focus(env, bindir, directory)
        require(not adapter.FAILURES, "; ".join(adapter.FAILURES))
        for failure in ("exit 1", "printf '%s\\n' invalid"):
            (bindir / "hyperlabctl").write_text("#!/bin/sh\n" + failure + "\n")
            for backend in ("sway", "hyprland"):
                result = subprocess.run(["bash", str(directory / "caller.sh"), backend],
                                        env=env, capture_output=True, text=True, timeout=10, check=False)
                require(result.returncode != 0 and not result.stdout,
                        "focus selected a window without a valid product name")


def main() -> int:
    qml_strings()
    name = cli_contract()
    deployment_contract()
    docs_contract(name)
    notification_contract(name)
    focus_contract()
    native_name_contract(name)
    shell_contract(name)
    print("Product display name contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
