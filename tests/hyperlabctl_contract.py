#!/usr/bin/env python
"""Structural contract between the cockpit and the repository it reads.

Discovered by verify.sh and by CI (`tests/*_contract.py`), so the CLI is gated
without a line being added to the workflow - which is the rule that file states
about itself.

Two jobs. It asserts the things that span the two halves of the cockpit and can
only be checked from here, and it runs the component's own suite, so a failure
inside tools/hyperlabctl is a failure of the repository.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "hyperlabctl"
sys.path.insert(0, str(TOOL))

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
    else:
        FAILED += 1
        print("  FAIL %s%s" % (name, " -- %s" % detail if detail else ""))


def waybar_config():
    raw = (REPO / "roles/desktop/files/waybar.jsonc").read_text()
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
    tasks = (REPO / "roles/desktop/tasks/main.yml").read_text()
    for module in modules:
        binary = module["exec"].split()[0]
        check("the role deploys %s" % binary, Path(binary).name in tasks)

    inspect_checkout = tasks.index("- name: Inspect the configured Hyperlab checkout before host writes")
    install_desktop = tasks.index("- name: Install the desktop stack")
    completion = tasks.index("- name: Generate shell completion from the subcommands that exist")
    install_completion = tasks.index("- name: Install the completion, when the CLI could produce one")
    completion_block = tasks[completion:install_completion]
    check("the checkout is refused before package writes", inspect_checkout < install_desktop)
    check("completion runs as the admin user", 'become_user: "{{ admin_user }}"' in completion_block)
    check("completion uses argv rather than a shell command", "argv:" in completion_block and "cmd:" not in completion_block)
    check("the checkout path must be absolute", "desktop_hyperlab_checkout is match('^/')" in tasks)

    palette = (REPO / "roles/desktop/files/privatestack-hyperlab-palette.sh").read_text()
    check("the palette never evals a resolved command", 'eval "$1"' not in palette)
    check("the palette executes validated JSON argv", '--json "${resolve_args[@]}"' in palette
          and "subprocess.call(argv)" in palette)


def component_suite():
    result = subprocess.run([sys.executable, str(TOOL / "tests" / "run.py")],
                            capture_output=True, text=True,
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
