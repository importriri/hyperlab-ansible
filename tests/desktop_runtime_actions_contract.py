#!/usr/bin/env python3
"""Structural contract for HyperLab runtime controls, screenshots and Create presets."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"desktop runtime actions contract: {message}")


def main() -> int:
    manager = text("roles/host_desktop_sway/files/privatestack-hyperlab-domains.py")
    registry = text("tools/hyperlabctl/hyperlabctl/registry.py")
    opener = text("tools/hyperlabctl/hyperlabctl/commands/open.py")
    composer = text("tools/hyperlabctl/hyperlabctl/composer.py")
    sway = text("roles/host_desktop_sway/files/sway.config")
    tasks = text("roles/host_desktop_sway/tasks/main.yml")
    screenshot = text("roles/host_desktop_sway/files/privatestack-screenshot.sh")
    arch = yaml.safe_load(text("images/arch.yml"))

    require("LayerShell.KeyboardMode.EXCLUSIVE" not in manager,
            "HyperLab must not keep exclusive keyboard focus")
    require("LayerShell.KeyboardMode.ON_DEMAND" in manager,
            "interactive surface must use on-demand keyboard focus")
    require(
        "notify::is-active" not in manager,
        "Layer Shell surfaces must not depend on compositor focus churn",
    )
    require(
        "class HyperlabBackdropWindow" not in manager
        and "LayerShell.KeyboardMode.NONE" not in manager
        and "backdrop.present()" not in manager,
        "outside dismissal still depends on the retired second surface",
    )
    require(
        "root = Gtk.Overlay()" in manager
        and "catcher = Gtk.Button()" in manager
        and 'lambda *_args: self.close_surface()' in manager
        and "root.add_overlay(panel)" in manager,
        "outside click is not owned by the active cockpit surface",
    )
    require(
        'Gtk.Button(label="LG")' in manager
        and 'looking_glass.set_tooltip_text("Looking Glass")' in manager
        and 'self._vm_action("vm.looking-glass", vm)' in manager,
        "compact drawer does not expose Looking Glass for eligible VMs",
    )
    require('self._vm_action("vm.ssh", vm)' in manager,
            "SSH button is not wired to the action registry")
    require('"vm.console", "vm.looking-glass", "vm.ssh"' in manager,
            "SSH/console/Looking Glass must launch outside the resident surface")
    require("self.close_surface()" in manager.split("def _vm_action", 1)[1].split("def _managed_action", 1)[0],
            "VM actions do not release the shell before launching")
    require("self.close_surface()" in manager.split("def _managed_action", 1)[1].split("def _destructive_managed", 1)[0],
            "managed actions do not release the shell before prompting")

    require('"id": "vm.ssh"' in registry and
            '["hyperlabctl", "open", "ssh", "{domain}"]' in registry,
            "vm.ssh registry action missing")
    require('"id": "vm.looking-glass"' in registry and
            '["hyperlabctl", "open", "looking-glass", "{domain}"]' in registry,
            "Looking Glass is not domain-targeted")
    require('sub.add_parser("ssh"' in opener and
            'ssh.add_argument("domain")' in opener,
            "SSH open command missing")
    require('looking.add_argument("domain")' in opener,
            "Looking Glass open command does not accept a domain")
    require(
        '"app:shmFile=/dev/kvmfr0"' in opener
        and '["looking-glass-client", "-F", "/dev/kvmfr0"]' not in opener,
        "Looking Glass client must use the valid B7 kvmfr0 shared-memory option",
    )
    require(
        'if transport == "linux-experimental":' in opener
        and 'argv.append("egl:mapHDRtoSDR=no")' in opener,
        "Linux experimental Looking Glass does not disable incorrect HDR tone mapping",
    )
    require(
        "def _looking_glass_transport(" in opener
        and "find_spec(" in opener
        and "image_entry(" in opener
        and "load_yaml(" in opener,
        "Looking Glass transport is not derived from the managed VM spec",
    )
    require(
        'os_family == "windows"' in opener
        and 'mode == "linux-experimental"' in opener,
        "Looking Glass does not separate Windows and Linux transports",
    )
    require(
        "def _prepare_linux_looking_glass(" in opener,
        "Linux Looking Glass lacks on-demand sender preparation",
    )

    prepare_script = opener.split(
        '_LINUX_LOOKING_GLASS_PREPARE = r"""',
        1,
    )[1].split('"""', 1)[0]

    prepare_function = opener.split(
        "def _prepare_linux_looking_glass(",
        1,
    )[1].split("\n\nclass ", 1)[0]

    require(
        "systemctl --user show-environment" in prepare_script
        and "HYPRLAND_INSTANCE_SIGNATURE" in prepare_script
        and "WAYLAND_DISPLAY" in prepare_script,
        "Linux sender preparation does not recover the Hyprland environment",
    )
    require(
        "Monitor HEADLESS-0" in prepare_script
        and "1920x1080@144" in prepare_script,
        "Linux sender preparation does not guard the reviewed capture output",
    )
    require(
        "/dev/kvmfr0" in prepare_script
        and "/usr/local/bin/looking-glass-host" in prepare_script,
        "Linux sender preparation does not guard the reviewed transport",
    )
    require(
        "sender_running" in prepare_script
        and "sender_pid=$!" in prepare_script
        and 'pgrep -u "$(id -u)" -x Hyprland' in prepare_script
        and 'kill "$sender_pid"' in prepare_script,
        "Linux sender is not session-bound and idempotent",
    )
    require(
        "pkill" not in prepare_script
        and ".service" not in prepare_script
        and "systemctl --user start" not in prepare_script,
        "Linux Looking Glass sender became persistent or restart-destructive",
    )
    require(
        "subprocess.run(" in prepare_function
        and 'input=_LINUX_LOOKING_GLASS_PREPARE' in prepare_function
        and 'timeout=20' in prepare_function,
        "Linux sender preparation is not bounded through strict SSH",
    )
    require(
        'if transport == "linux-experimental":' in opener
        and "sender_ready = _prepare_linux_looking_glass(" in opener
        and "_wait_for_linux_looking_glass_login(" in opener,
        "Linux Looking Glass client bypasses the PRIMARY login handoff",
    )

    launch = opener.split(
        "transport = _looking_glass_transport(ctx, args.domain)",
        1,
    )[1]

    require(
        launch.index(
            "sender_ready = _prepare_linux_looking_glass("
        )
        < launch.index(
            '"app:shmFile=/dev/kvmfr0"'
        ),
        "Looking Glass client can start before Linux sender preparation",
    )
    require("ansible_ssh_common_args" in opener and
            "StrictHostKeyChecking" not in opener,
            "SSH must consume strict generated inventory instead of duplicating options")

    require("privatestack-screenshot.sh" in tasks,
            "screenshot helper is not deployed by the role")
    require("bindsym Print exec /usr/local/bin/privatestack-screenshot full" in sway,
            "Print does not capture the full screen")
    require("bindsym Shift+Print exec /usr/local/bin/privatestack-screenshot region" in sway,
            "Shift+Print does not capture a selected region")
    require("bindsym Ctrl+Print exec /usr/local/bin/privatestack-screenshot region choose" in sway,
            "Ctrl+Print does not offer Save as")
    for marker in (
        "grim", "slurp", "wl-copy --type image/png", "/Screenshots",
        "rofi -dmenu -p 'Save screenshot as'",
    ):
        require(marker in screenshot, f"screenshot helper missing: {marker}")

    require('"arch-minimal"' in manager and "CREATE_PRESETS" in manager,
            "Create does not expose the validated arch-minimal preset")
    for marker in ('"image": "arch"', '"lifecycle": "disposable"',
                   '"device": "standard"', '"network": "dev"',
                   '"resource": "minimum"'):
        require(marker in manager, f"arch-minimal preset missing: {marker}")
    require('order = ("clean", "dev", "services", "dirty", "lab")' in manager,
            "Create does not render every real segment")
    require(arch["network_allowlist"] == ["clean", "dev", "dirty", "lab", "services"],
            "Arch manifest does not permit all five standard segments")
    require('device_profile == "vfio" and value == "services"' in composer,
            "services must remain structurally excluded from VFIO")

    print("HyperLab desktop runtime actions contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
