#!/usr/bin/env python3
"""Structural contract for shared host desktop compositor primitives."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"host desktop common contract: {message}")


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def check_networks_deployment(shared: dict) -> None:
    flag = "host_desktop_common_networks_view_enabled"
    require(shared.get(flag) is False, "Networks feature must default to boolean false")
    tasks = yaml.safe_load(text("roles/host_desktop_common/tasks/main.yml"))
    assertions = [task for task in tasks if flag + " is boolean" in
                  task.get("ansible.builtin.assert", {}).get("that", [])]
    require(len(assertions) == 1, "Networks flag needs one boolean validation")
    copies = [task for task in tasks if task.get("ansible.builtin.copy", {})
              .get("dest", "").endswith("/features.json")]
    require(len(copies) == 1, "Networks feature document needs one installation")
    copy = copies[0]["ansible.builtin.copy"]
    require(copy["dest"] == "{{ host_desktop_common_shell_stage.config_root }}/features.json"
            and copy["owner"] == "root" and copy["group"] == "root"
            and copy["mode"] == "0644", "Networks feature document deployment changed")
    first_install = next(i for i, task in enumerate(tasks)
                         if "community.general.pacman" in task)
    require(tasks.index(assertions[0]) < first_install,
            "Networks flag validation must precede installation")
    # Execute the actual assertion and copy content in a disposable local
    # play. Only destination and ownership are adapted; no role is applied.
    with tempfile.TemporaryDirectory(prefix="hyperlab-features-") as raw:
        directory = Path(raw)
        output = directory / "features.json"
        task_copy = {key: value for key, value in copy.items()
                     if key not in ("owner", "group")}
        task_copy["dest"] = str(output)
        play = directory / "features.yml"
        play.write_text(yaml.safe_dump([{
            "name": "Check feature document", "hosts": "localhost",
            "gather_facts": False, "tasks": [assertions[0], {
                "name": "Stage feature JSON", "ansible.builtin.copy": task_copy}]
        }]))
        for value in (False, True, "false", "true", 0, 1, None, [], {}):
            output.unlink(missing_ok=True)
            result = subprocess.run([
                "ansible-playbook", "-i", "localhost,", "-c", "local", str(play),
                "--extra-vars", json.dumps({flag: value})],
                env={**os.environ, "ANSIBLE_NOCOLOR": "1"}, capture_output=True,
                text=True, timeout=60, check=False)
            if type(value) is bool:
                require(result.returncode == 0 and output.is_file(),
                        f"Networks boolean did not render: {value}: {result.stdout}")
                document = json.loads(output.read_text())
                require(document == {"networks_view_enabled": value}
                        and type(document["networks_view_enabled"]) is bool
                        and output.stat().st_mode & 0o777 == 0o644,
                        f"Networks generated document differs: {document}")
            else:
                require(result.returncode != 0 and not output.exists(),
                        f"Networks nonboolean reached installation: {value!r}")
                marker = "FAILED! => "
                require(marker in result.stdout,
                        f"Networks refusal did not report its assertion: {result.stdout}")
                failure, _ = json.JSONDecoder().raw_decode(result.stdout.split(marker, 1)[1])
                require(failure.get("assertion") == flag + " is boolean"
                        and failure.get("evaluated_to") is False,
                        f"Networks refusal failed for an unrelated reason: {failure}")


def main() -> int:
    graph = yaml.safe_load(text("group_vars/all/bricks.yml"))
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )

    check_networks_deployment(shared)

    product = shared["host_desktop_common_product_contract"]
    trust = shared["host_desktop_common_trust_contract"]
    parity = shared["host_desktop_common_required_parity"]

    require(
        product["preferred_compositor"] == "hyprland",
        "Hyprland is no longer the preferred compositor",
    )
    require(
        product["supported_compositors"] == ["hyprland", "sway"],
        "supported compositor set or order changed",
    )
    require(
        product["recovery_compositor"] == "sway",
        "Sway is no longer the recovery compositor",
    )
    require(
        product["parity_required"] is True,
        "cross-compositor product parity became optional",
    )
    require(
        product["trust_compositor_independent"] is True
        and product["themes_compositor_independent"] is True,
        "trust or themes became compositor-specific",
    )
    require(
        product["shell"]
        == {
            "primary": "quickshell",
            "phase": 2,
            "scope": "shared",
            "fake_controls_allowed": False,
            "backend_authority": [
                "hyperlabctl",
                "specs",
                "contracts",
            ],
        },
        "shared HyperLab Shell contract changed",
    )

    stage = shared["host_desktop_common_shell_stage"]

    require(
        stage["implementation"] == "quickshell"
        and stage["config_name"] == "hyperlab"
        and stage["config_root"]
        == "/etc/xdg/quickshell/hyperlab",
        "shared shell deployment identity changed",
    )
    require(
        stage["reviewed_api_series"] == "0.3",
        "reviewed Quickshell API series changed",
    )
    require(
        stage["runtime_enabled"] is False
        and stage["replacement_enabled"] is False,
        "Phase 2A unexpectedly activates the shared shell",
    )
    require(
        stage["waybar_fallback_required"] is True
        and stage["gtk_surface_fallback_required"] is True,
        "Phase 2A recovery surfaces became optional",
    )
    require(
        stage["compositor_specific_imports_allowed"] is False,
        "shared shell may import a compositor-specific API",
    )
    require(
        product["shared_surfaces"]
        == [
            "trust-model",
            "themes",
            "hyperlab-shell",
            "control-center",
            "drawers",
            "vm-workflows",
            "wallpaper-policy",
            "keyboard-policy",
            "lock-policy",
            "power-controls",
            "security-semantics",
        ],
        "shared product surface set changed",
    )

    require(
        trust["owner"] == "host"
        and trust["guest_self_assignment"] is False,
        "trust authority left the host",
    )
    require(
        {
            name: value["level"]
            for name, value in trust["classes"].items()
            if name != "services"
        }
        == {
            "clean": 3,
            "dev": 2,
            "dirty": 1,
            "lab": 0,
        },
        "shared trust ladder changed",
    )
    require(
        trust["classes"]["services"]["gpu_trust_rung"] is False,
        "services became a GPU trust rung",
    )

    require(
        parity
        == [
            "workspaces-1-9",
            "move-to-workspace",
            "focus-move-resize",
            "fullscreen",
            "floating",
            "terminal",
            "file-manager",
            "launcher",
            "power-menu",
            "hyperlab-drawer",
            "hyperlab-diagnostics",
            "hyperlab-control-center",
            "hyperlab-doctor",
            "looking-glass",
            "spice-console",
            "audio-125",
            "audio-mute",
            "brightness",
            "screenshot-full",
            "screenshot-region",
            "keyboard-cycle",
            "machine-theme-key",
            "theme-cycle",
            "wallpaper-mode",
            "wallpaper-daemon",
            "lock",
            "idle-dpms",
        ],
        "required compositor parity set changed",
    )

    require(
        graph["brick_requires"]["host_desktop_common"] == [],
        "common brick must have no compositor prerequisite",
    )
    require(
        graph["brick_requires"]["host_desktop_sway"]
        == ["host_desktop_common"],
        "Sway must consume the shared host desktop primitive",
    )
    require(
        graph["brick_requires"]["host_desktop_hyprland"]
        == ["host_desktop_sway"],
        "Hyprland must preserve the proven Sway fallback chain",
    )
    require(
        graph["brick_playbooks"]["host_desktop_common"]
        == "playbooks/host-desktop-common.yml",
        "common brick mount changed",
    )

    common_play = yaml.safe_load(
        text("playbooks/host-desktop-common.yml")
    )
    require(
        common_play[0]["roles"] == ["host_desktop_common"],
        "common playbook must mount only the common brick",
    )

    sway_play = yaml.safe_load(
        text("playbooks/host-desktop-sway.yml")
    )[0]
    roles = sway_play["roles"]

    require(
        roles[0] == "host_desktop_common",
        "common brick must land before Sway",
    )
    require(
        isinstance(roles[1], dict)
        and roles[1].get("role") == "brick_guard"
        and roles[1].get("vars", {}).get("brick_guard_brick")
        == "host_desktop_sway",
        "Sway prerequisite guard is missing",
    )
    require(
        roles[2] == "host_desktop_sway",
        "Sway role order changed",
    )

    lab = yaml.safe_load(text("playbooks/lab.yml"))
    require(
        len(lab) == 2
        and lab[0].get("import_playbook") == "foundation.yml",
        "lab.yml foundation boundary changed",
    )

    lab_roles = lab[1].get("roles", [])

    require(
        len(lab_roles) == 5,
        "lab.yml cockpit role count changed",
    )
    require(
        lab_roles[0] == "host_desktop_common",
        "lab.yml does not mount the common desktop primitive first",
    )
    require(
        isinstance(lab_roles[1], dict)
        and lab_roles[1].get("role") == "brick_guard"
        and lab_roles[1].get("vars", {}).get("brick_guard_brick")
        == "host_desktop_sway",
        "lab.yml does not guard the Sway dependency",
    )
    require(
        lab_roles[2] == "host_desktop_sway",
        "lab.yml lost the proven Sway cockpit",
    )
    require(
        isinstance(lab_roles[3], dict)
        and lab_roles[3].get("role") == "brick_guard"
        and lab_roles[3].get("vars", {}).get("brick_guard_brick")
        == "looking_glass",
        "lab.yml Looking Glass prerequisite guard changed",
    )
    require(
        lab_roles[4] == "looking_glass",
        "lab.yml lost the Looking Glass host role",
    )

    common_tasks = text(
        "roles/host_desktop_common/tasks/main.yml"
    )
    require(
        "privatestack-compositor-adapter.sh" in common_tasks
        and "/usr/local/bin/privatestack-compositor-adapter"
        in common_tasks,
        "common adapter deployment missing",
    )
    require(
        "brick_guard_brick: host_desktop_common" in common_tasks,
        "common brick stamp missing",
    )

    require(
        (
            ROOT
            / "roles/host_desktop_common/files"
            / "privatestack-compositor-adapter.sh"
        ).is_file(),
        "shared adapter source missing",
    )
    require(
        not (
            ROOT
            / "roles/host_desktop_hyprland/files"
            / "privatestack-compositor-adapter.sh"
        ).exists(),
        "adapter still belongs to the Hyprland-specific role",
    )

    helper_paths = (
        "roles/host_desktop_sway/files/privatestack-keyboard.sh",
        "roles/host_desktop_sway/files/privatestack-theme.sh",
        "roles/host_desktop_sway/files/privatestack-controls.sh",
        "roles/host_desktop_common/files/privatestack-opacity-toggle.sh",
        "roles/host_desktop_sway/files/privatestack-waybar.sh",
        "roles/host_desktop_sway/files/privatestack-powermenu.sh",
        "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py",
    )

    for path in helper_paths:
        source = text(path)
        require(
            "swaymsg" not in source,
            f"high-level helper still owns Sway IPC: {path}",
        )
        require(
            "hyprctl" not in source,
            f"high-level helper owns Hyprland IPC: {path}",
        )

    require(
        "privatestack-compositor-adapter"
        in text(
            "roles/host_desktop_sway/files/"
            "privatestack-keyboard.sh"
        ),
        "keyboard helper does not use adapter",
    )
    require(
        "privatestack-compositor-adapter"
        in text(
            "roles/host_desktop_sway/files/"
            "privatestack-theme.sh"
        ),
        "theme helper does not use adapter",
    )

    generic_lock = text(
        "roles/host_desktop_common/files/privatestack-lock.sh"
    )
    legacy_lock = text(
        "roles/host_desktop_sway/files/privatestack-swaylock.sh"
    )

    require(
        "privatestack-theme lock-image" in generic_lock
        and "swaylock" in generic_lock
        and "hyprlock" in generic_lock,
        "generic lock does not preserve both compositor backends",
    )
    require(
        "exec /usr/local/bin/privatestack-lock" in legacy_lock,
        "legacy Sway lock entry point is not a compatibility wrapper",
    )

    sway = text("roles/host_desktop_sway/files/sway.config")
    require(
        "/usr/local/bin/privatestack-lock" in sway,
        "Sway config does not use generic lock entry point",
    )
    require(
        "/usr/local/bin/privatestack-swaylock" not in sway,
        "live Sway config still depends on legacy lock name",
    )

    guest_defaults = text(
        "roles/guest_desktop_hyprland/defaults/main.yml"
    )
    require(
        "/usr/local/bin/privatestack-lock" in guest_defaults
        and "/usr/local/bin/privatestack-compositor-adapter"
        in guest_defaults,
        "guest host-artifact cleanup is incomplete",
    )

    print("HyperLab host desktop common contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
