#!/usr/bin/env python3
"""Verify the shared product name at the presentation boundaries."""
from __future__ import annotations

import argparse
import ast
import configparser
import io
import json
import os
import re
import shlex
import shutil
from shlex import quote as shlex_quote
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
SESSIONS = "the HyperLab Hyprland and HyperLab Sway sessions in Ly's private catalog"
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

    name, byline = cli._product_info(PRODUCT)
    require(byline == yaml.safe_load(PRODUCT.read_text())["byline"], "CLI/shared byline drift")
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
        for raw in ('', '{}', '{"name":"A","name":"B","byline":"by C"}', '{"name":null,"byline":"by B"}',
                    '{"name":"Bad\\nname","byline":"by B"}', '{"name":"A","other":1}',
                    '{"name":"A","byline":null}',
                    '{"name":"A","byline":"by B"}\n\n',
                    '{"name":"A","byline":"by B"}\x00',
                    '{"name":"A","byline":"' + "B" * 65 + '"}',
                    '{"name":"A","byline":"by B","byline":"by C"}'):
            path.write_text(raw)
            try:
                cli._product_info(path)
            except cli.HyperlabError:
                pass
            else:
                raise AssertionError(f"accepted invalid product input: {raw!r}")
        path.write_text('{"name":"Example Name","byline":"by Example"}\n')
        require(cli._product_info(path) == ("Example Name", "by Example"), "name source cannot change independently")
        path.chmod(0)
        try:
            cli._product_info(path)
        except cli.HyperlabError:
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
                cli._product_info(bad)
            except cli.HyperlabError:
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
        if filename == "README.md":
            require(source.count(SESSIONS) == 1, "README does not name the installed greeter sessions")
            source = source.replace(SESSIONS, "")
        # Code identifiers such as HYPERLAB_REQUIRE_QML_RUNTIME keep their
        # spelling; a product word in prose or a diagram does not.
        require(not re.search(r"\b(?:HyperLab|Hyperlab|HYPERLAB)\b", source.replace(HISTORY, "")),
                f"{filename}: old product prose")


def deferred_surface_contract() -> None:
    """Pin the documented visible exceptions while their migration is pending."""
    entries = {
        "roles/host_desktop_hyprland/files/hyperlab-hyprland.desktop": "HyperLab Hyprland",
        "roles/host_desktop_hyprland/files/hyperlab-sway.desktop": "HyperLab Sway",
        "roles/host_desktop_sway/files/hyperlab-control-center.desktop": "HyperLab Control Center",
    }
    inventory = [*entries,
        "roles/host_desktop_sway/files/waybar.jsonc",
        "roles/host_desktop_sway/files/privatestack-swaybar-status.py",
        "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py",
        "roles/host_desktop_sway/files/privatestack-theme.sh",
        "roles/host_desktop_sway/files/privatestack-controls.sh",
        "roles/host_desktop_common/files/privatestack-machine-actions.py",
        "roles/host_desktop_common/files/privatestack-operation.py",
        "roles/host_vault/files/hyperlab-vault-confirm.py",
        "roles/guest_desktop_hyprland/files/hyperlab-clipboard-receive.py",
        "tools/hyperlabctl/hyperlabctl/hardware.py",
    ]
    roadmap = (ROOT / "docs/roadmap.md").read_text()
    open_items = re.findall(r"(?m)^- \[ \] Finish the visible name migration[^\n]*(?:\n +[^\n]*)*", roadmap)
    require(len(open_items) == 1, "deferred visible migration is not open exactly once")
    adr = (ROOT / "docs/adr/0058-visible-name-migration-boundary.md").read_text()
    for filename in inventory:
        require((ROOT / filename).is_file(), f"missing deferred surface: {filename}")
        for label, source in (("open roadmap item", open_items[0]), ("ADR 0058", adr)):
            require(f"`{Path(filename).name}`" in source,
                    f"visible legacy surface omitted from {label}: {filename}")
    bridge = ROOT / "roles/host_desktop_common/files/privatestack-machine-actions.py"
    reasons = {
        "invalid HyperLab spec inventory",
        "machine maps to more than one HyperLab spec",
        "managed action has no HyperLab spec",
        "this managed machine's HyperLab spec is unavailable",
        "machine metadata and HyperLab spec disagree",
        "invalid HyperLab checkout",
    }
    for node in ast.walk(ast.parse(bridge.read_text())):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "Refused":
            continue
        for argument in node.args:
            text = "".join(part.value for part in ast.walk(argument)
                           if isinstance(part, ast.Constant) and isinstance(part.value, str))
            if OLD.search(text):
                require(text in reasons, f"new old-name bridge refusal outside inventory: {text}")
                require(f"`{text}`" in adr, f"bridge refusal omitted from ADR inventory: {text}")
    for filename, expected in entries.items():
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string((ROOT / filename).read_text())
        require(parser["Desktop Entry"]["Name"] == expected, f"undocumented greeter/application name: {filename}")
    source = (SWAY_FILES / "waybar.jsonc").read_text()
    bar = json.loads(re.sub(r"(?m)^\s*//[^\n]*", "", source))["custom/brand"]
    require(bar["format"] == "  HyperLab" and bar["tooltip-format"] == "Open the compact HyperLab drawer",
            "undocumented fallback bar brand/tooltip")


DEPLOYED_PRODUCT = "/etc/xdg/quickshell/hyperlab/product.yml"
SWAY_FILES = ROOT / "roles/host_desktop_sway/files"


def bash_function(source: str, function: str) -> str:
    match = re.search(r"^" + function + r"\(\) \{\n.*?^\}", source, re.M | re.S)
    require(match is not None, f"missing Bash function: {function}")
    return match[0]


def bash_reader_contract() -> None:
    """Keep standalone deployed readers identical and reject redirected parents."""
    readers = [ROOT / "roles/host_desktop_common/files/privatestack-compositor-adapter.sh",
               *(SWAY_FILES / name for name in ("privatestack-keyboard.sh", "privatestack-theme.sh",
                                               "privatestack-waybar.sh"))]
    bodies = [bash_function(path.read_text(), "product_name") for path in readers]
    require(all(body == bodies[0] for body in bodies), "Bash product_name readers differ")
    with tempfile.TemporaryDirectory(prefix="product-parent-") as temporary:
        directory = Path(temporary)
        product = directory / "product.yml"
        product.write_bytes(PRODUCT.read_bytes())
        parent = directory / "redirected"
        parent.symlink_to(directory, target_is_directory=True)
        for path, body in zip(readers, bodies, strict=True):
            script = body.replace(DEPLOYED_PRODUCT, str(parent / product.name)) + "\nproduct_name"
            result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
            require(result.returncode != 0 and not result.stdout,
                    f"{path.name}: symlinked product parent accepted")


def notification_contract(name: str) -> None:
    """The deployed identity wins over missing, stale or broken CLI checkouts."""
    with tempfile.TemporaryDirectory(prefix="product-notify-") as temporary:
        directory = Path(temporary)
        product = directory / "product.yml"
        product.write_bytes(PRODUCT.read_bytes())
        recorder = directory / "notify-send"
        recorder.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
        recorder.chmod(0o755)
        command = directory / "hyperlabctl"
        env = {**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"]}
        for filename, function, call in (
            ("privatestack-theme.sh", "notify", 'notify "Theme changed"'),
            ("privatestack-keyboard.sh", "notify_layout", 'notify_layout "us"'),
            ("privatestack-waybar.sh", "notify_bar_failure", 'notify_bar_failure'),
        ):
            source = (SWAY_FILES / filename).read_text().replace(DEPLOYED_PRODUCT, str(product))
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
            helpers = bash_function(source, "product_name") if "product_name() {" in source else ""
            script = helpers + "\n" + bash_function(source, function) + "\n" + call
            for stub in ("printf '%s\\n' 'hyperlabctl 0.1.0'", "exit 1", "exit 127"):
                command.write_text('#!/bin/sh\n' + stub + '\n')
                command.chmod(0o755)
                result = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                                        text=True, check=False)
                require(result.returncode == 0, f"{filename}: notification depends on CLI: {result.stderr}")
                argv = json.loads(result.stdout)
                require(argv[argv.index("--app-name") + 1] == name, f"{filename}: wrong notification app name")
                require(not any(OLD.search(value) for value in argv), f"{filename}: old notification text")
            for raw in ("{}", '{"name":"A","name":"B","byline":"by C"}',
                        '{"name":"A","byline":"by B","byline":"by C"}',
                        '{"name":"A","byline":null}', PRODUCT.read_text() + '{}',
                        PRODUCT.read_text() + '\n', PRODUCT.read_text() + '\x00',
                        '{"name":"A","byline":"' + "B" * 65 + '"}'):
                product.write_text(raw)
                refused = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                                         text=True, check=False)
                require(refused.returncode != 0 and not refused.stdout,
                        f"{filename}: notification defaulted after invalid product input")
            product.write_bytes(PRODUCT.read_bytes())
            saved = directory / "saved.yml"
            product.rename(saved)
            product.symlink_to(saved)
            refused = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                                     text=True, check=False)
            require(refused.returncode != 0 and not refused.stdout, f"{filename}: redirected name accepted")
            product.unlink()
            saved.rename(product)
            parent = directory / "redirected"
            parent.symlink_to(directory, target_is_directory=True)
            refused = subprocess.run(["bash", "-c", script.replace(str(product), str(parent / product.name))],
                                     env=env, capture_output=True, text=True, check=False)
            require(refused.returncode != 0 and not refused.stdout,
                    f"{filename}: notification accepted symlinked product parent")
            parent.unlink()
            product.unlink()
            missing = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                                     text=True, check=False)
            require(missing.returncode != 0 and not missing.stdout, f"{filename}: missing name accepted")
            product.mkdir()
            nonregular = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                                        text=True, check=False)
            require(nonregular.returncode != 0 and not nonregular.stdout, f"{filename}: directory name accepted")
            product.rmdir()
            product.write_bytes(PRODUCT.read_bytes())


def operation_contract() -> None:
    """Execute real operations with inert actuation and a broken name input."""
    with tempfile.TemporaryDirectory(prefix="product-operation-") as temporary:
        directory = Path(temporary)
        for program, body in (("hyperlabctl", "exit 1"), ("pkill", "exit 0"),
                              ("adapter", "exit 0"), ("notify-send", "echo NOTIFIED")):
            adapter.write_executable(directory / program, "#!/bin/sh\n" + body + "\n")
        env = {**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"],
               "XDG_CONFIG_HOME": str(directory / "config"),
               "HYPERLAB_COMPOSITOR_ADAPTER": str(directory / "adapter")}
        product = directory / "missing.yml"
        keyboard = directory / "keyboard.sh"
        keyboard.write_text((SWAY_FILES / "privatestack-keyboard.sh").read_text().replace(
            DEPLOYED_PRODUCT, str(product)))
        result = subprocess.run(["bash", str(keyboard), "set", "us"], env=env,
                                capture_output=True, text=True, check=False)
        require((directory / "config/hyperlab/keyboard-layout").read_text().strip() == "us",
                "layout state was not saved")
        require(result.returncode == 0 and not result.stdout and "notification withheld:" in result.stderr,
                f"notification failure changed layout success: {result.returncode}: {result.stdout}{result.stderr}")
        theme = (SWAY_FILES / "privatestack-theme.sh").read_text().replace(DEPLOYED_PRODUCT, str(product))
        functions = "\n".join(bash_function(theme, name) for name in (
            "notify", "set_theme", "set_mode", "set_rgb_mode", "next_wallpaper"))
        if "product_name() {" in theme:
            functions = bash_function(theme, "product_name") + "\n" + functions
        # Retain the complete operation bodies; replace only their external
        # dependencies, so notification call-site regressions remain visible.
        prelude = '''
set -euo pipefail
valid_theme() { return 0; }
valid_mode() { return 0; }
valid_rgb_mode() { return 0; }
write_atomic() { printf '%s\n' "$2" > "$1"; }
install_active_palette() { :; }
set_desktop_wallpaper() { :; }
reload_palette_consumers() { :; }
signal_quickshell_appearance() { :; }
signal_wallpaper_mode() { :; }
signal_controls() { :; }
current_theme() { printf 'green'; }
current_mode() { printf 'public'; }
read_index() { printf '0'; }
active_wallpaper_count() { printf '20'; }
personal_wallpaper_path() { printf '/nonexistent'; }
'''
        for call in ('set_theme blue', 'set_mode public', 'set_mode personal',
                     'set_rgb_mode off', 'set_rgb_mode focus-trust', 'next_wallpaper'):
            state = directory / "operation-state"
            setup = (f"theme_file={shlex_quote(str(state))}\n"
                     f"wallpaper_mode_file={shlex_quote(str(state))}\n"
                     f"rgb_mode_file={shlex_quote(str(state))}\n"
                     f"desktop_index_file={shlex_quote(str(directory / 'index'))}\n"
                     f"compositor_adapter={shlex_quote(str(directory / 'adapter'))}\n")
            result = subprocess.run(["bash", "-c", prelude + setup + functions + "\n" + call],
                                    env=env, capture_output=True, text=True, check=False)
            require(result.returncode == 0 and not result.stdout and "notification withheld:" in result.stderr,
                    f"{call}: cosmetic failure changed operation success: {result.stdout}{result.stderr}")
        waybar = (SWAY_FILES / "privatestack-waybar.sh").read_text().replace(DEPLOYED_PRODUCT, str(product))
        functions = "\n".join(bash_function(waybar, name) for name in (
            "notify_bar_failure", "start"))
        if "product_name() {" in waybar:
            functions = bash_function(waybar, "product_name") + "\n" + functions
        adapter.write_executable(directory / "waybar", "#!/bin/sh\nexit 1\n")
        setup = f'''
state_dir={shlex_quote(str(directory))}
pid_file={shlex_quote(str(directory / "pid"))}
log={shlex_quote(str(directory / "bar.log"))}
config=unused
style=unused
stopping=0
acquire_supervisor_lock() {{ return 0; }}
retire_legacy_supervisor() {{ return 0; }}
cleanup() {{ :; }}
stop_supervisor() {{ :; }}
native_bar() {{ printf 'fallback restored\n'; }}
hide_native_bar() {{ :; }}
sleep() {{ :; }}
'''
        result = subprocess.run(["bash", "-c", setup + functions + "\nstart"], env=env,
                                capture_output=True, text=True, check=False, timeout=10)
        require(result.returncode == 0 and result.stdout.strip() == "fallback restored"
                and "notification withheld:" in result.stderr,
                f"bar fallback success changed by notification failure: {result.stdout}{result.stderr}")


def cli_refusal_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="product-cli-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "tools/hyperlabctl", directory / "hyperlabctl",
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        path = directory / "product.yml"
        runtime_dir = directory / "run"
        runtime_dir.mkdir(mode=0o700)
        env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime_dir),
               "XDG_CONFIG_HOME": str(directory / "config")}
        command = [sys.executable, str(directory / "hyperlabctl/bin/hyperlabctl")]

        def check_dispatch() -> None:
            # Status reads only this fixture's empty runtime directory, with no
            # compositor, libvirt or emergency-stop actuation.
            result = subprocess.run([*command, "panic", "status"], env=env,
                                    capture_output=True, text=True, check=False)
            require(result.returncode == 0 and result.stdout.strip() == "No emergency stop is engaged."
                    and not result.stderr,
                    f"display input blocked emergency-stop dispatch: {result.stdout}{result.stderr}")
            for args in (("--version",), ("--help",), ("panic", "--help")):
                result = subprocess.run([*command, *args], env=env,
                                        capture_output=True, text=True, check=False)
                require(result.returncode == 2
                        and result.stderr.strip() == "hyperlabctl: invalid product name input" and not result.stdout,
                        f"invalid display input escaped CLI refusal boundary ({args}): {result.stderr}")

        for raw in (None, "{}", '{"name":"A","name":"B","byline":"by C"}',
                    '{"name":"A","byline":null}', '{"name":"Sfère","byline":"by D"}'):
            if raw is not None:
                path.write_text(raw)
            check_dispatch()
        path.unlink()
        path.symlink_to(PRODUCT)
        check_dispatch()


def help_source_contract() -> None:
    allowed = {
        ("doctor.py", "help", "whether this computer can run HyperLab, read without privilege"),
        ("open.py", "help", "open fixed graphical HyperLab shell surfaces"),
    }
    observed: set[tuple[str, str, str]] = set()
    for path in sorted((ROOT / "tools/hyperlabctl/hyperlabctl/commands").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            values = []
            if isinstance(node, ast.keyword) and node.arg in ("help", "description"):
                values = [(node.arg, node.value)]
            elif isinstance(node, ast.Assign):
                values = [(target.id, node.value) for target in node.targets
                          if isinstance(target, ast.Name) and target.id in ("help", "description")]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in ("help", "description") and node.value is not None:
                    values = [(node.target.id, node.value)]
            for field, value in values:
                # Fold constant concatenation as well as ordinary string literals.
                literals = [part.value for part in ast.walk(value)
                            if isinstance(part, ast.Constant) and isinstance(part.value, str)]
                text = "".join(literals)
                if OLD.search(text):
                    entry = (path.name, field, text)
                    require(entry in allowed, f"{path.name}: new old-name help source: {text}")
                    observed.add(entry)
    require(observed == allowed, "existing help exceptions changed; update their explicit inventory")


SCENARIO = r'''
            const expected = @@NAME@@;
            check(sharedState.productName === expected, "shell/shared name drift");
            check(sharedState.productByline === @@BYLINE@@, "product byline drift");
            function texts(item) {
                let result = [];
                if (item.text !== undefined) result.push(String(item.text));
                if (item.Accessible) {
                    result.push(String(item.Accessible.name), String(item.Accessible.description));
                }
                for (const child of item.children || []) result = result.concat(texts(child));
                return result;
            }
            check(texts(rail).includes(expected), "bar does not display shared product name");
            check(texts(desktop).includes(expected), "desktop does not display shared product name");
            check(texts(desktop).includes(@@BYLINE@@), "desktop byline missing");
            sharedSurfaces.openLauncher("");
            for (const surface of [rail, desktop, launcher]) {
                check(!texts(surface).some(text => /HyperLab|Hyperlab|HYPERLAB/.test(text)),
                      "bar, desktop or launcher renders an old product display string");
            }
            sharedSurfaces.closeLauncher();
            for (const destination of ["machines", "controls", "diagnostics", "workbench", "devices"]) {
                sharedSurfaces.openWorkspace(destination);
                check(workspaceSurface.title.startsWith(expected + " · "), "window title drift");
                check(!texts(workspaceSurface).some(text => /HyperLab|Hyperlab|HYPERLAB/.test(text)),
                      "workspace renders an old product display string");
            }
            check(launcher.hostKeys.productName === expected, "key-sheet name binding missing");
            check(launcher.hostKeys.groups[0].title === expected, "key-sheet product title drift");
            for (const raw of ["", "{}", '{"name":"A","name":"B","byline":"by C"}', '{"name":null,"byline":"by B"}',
                               '{"name":"A","other":1}', '{"name":"Bad\\nname","byline":"by B"}']) {
                check(sharedState.parseProduct(raw) === null, "shell accepted invalid product input");
            }
            check(sharedState.parseProduct('{"name":"Example Name","byline":"by Example"}').name === "Example Name",
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
            body = SCENARIO.replace("@@NAME@@", json.dumps(name)).replace(
                "@@BYLINE@@", json.dumps(yaml.safe_load(PRODUCT.read_text())["byline"]))
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
        onTriggered: { console.log("PRODUCT_RESULT=" + JSON.stringify([state.productName, state.productByline])); Qt.quit(); }
    }
}
'''
        (directory / "shell.qml").write_text(scene)
        for raw, expected in ((PRODUCT.read_text(), [name, yaml.safe_load(PRODUCT.read_text())["byline"]]),
                              ('{"name":"Example Name","byline":"by Example"}', ["Example Name", "by Example"]),
                              ('{"name":"A","name":"B","byline":"by C"}', ["", ""]),
                              ('{"name":"A","byline":"by B","byline":"by C"}', ["", ""]),
                              ('{"name":"A","byline":null}', ["", ""]),
                              ("{}", ["", ""]), (None, ["", ""])):
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
            records = re.findall(r'PRODUCT_RESULT=(\[[^\n]*\])', output)
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



def main() -> int:
    qml_strings()
    cli_refusal_contract()
    help_source_contract()
    name = cli_contract()
    deployment_contract()
    docs_contract(name)
    deferred_surface_contract()
    bash_reader_contract()
    notification_contract(name)
    focus_contract()
    operation_contract()
    native_name_contract(name)
    shell_contract(name)
    print("Product display name contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
