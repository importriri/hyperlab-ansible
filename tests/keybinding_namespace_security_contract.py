#!/usr/bin/env python3
"""Host/guest keyboard namespace and guest disclosure boundary."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab keybinding security contract: {message}"
        )


def bind_first_arguments(source: str) -> list[str]:
    return re.findall(
        r"hl\.bind\(\s*\n?\s*([^,\n]+)",
        source,
    )


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )

    policy = shared["host_desktop_common_input_security"]

    require(
        policy["host_primary_modifier"] == "SUPER",
        "host primary modifier changed",
    )
    require(
        policy["guest_primary_modifier"] == "ALT",
        "guest primary modifier changed",
    )
    require(
        policy["host_primary_modifier"]
        != policy["guest_primary_modifier"],
        "host and guest primary modifier namespaces overlap",
    )
    require(
        policy["modifiers_must_differ"] is True,
        "modifier separation became optional",
    )
    require(
        policy["looking_glass_escape_key"]
        == "KEY_RIGHTCTRL",
        "Looking Glass transport escape changed",
    )

    require(
        policy["guest_exposure_default"] == "deny",
        "guest disclosure policy is no longer default deny",
    )
    require(
        policy["guest_allowed_exposure"]
        == ["guest-local", "transport-safe"],
        "guest allowed exposure classes changed",
    )
    require(
        policy["guest_forbidden_exposure"]
        == [
            "host-only",
            "privileged",
            "recovery-sensitive",
            "hypervisor-internal",
        ],
        "guest forbidden exposure classes changed",
    )

    for key in (
        "guest_may_receive_host_inventory",
        "guest_may_receive_other_domain_inventory",
        "guest_may_receive_host_paths",
        "guest_may_receive_host_network_topology",
        "guest_may_receive_hypervisor_control_routes",
    ):
        require(
            policy[key] is False,
            f"guest information boundary weakened: {key}",
        )

    sway = text(
        "roles/host_desktop_sway/files/sway.config"
    )
    host_hypr = text(
        "roles/host_desktop_hyprland/templates/hyprland.lua.j2"
    )
    guest_hypr = text(
        "roles/guest_desktop_hyprland/templates/hyprland.lua.j2"
    )
    looking_glass = text(
        "roles/looking_glass/defaults/main.yml"
    )

    require(
        "set $mod Mod4" in sway,
        "Sway host namespace is no longer SUPER/Mod4",
    )
    require(
        'local main_mod = "SUPER"' in host_hypr,
        "Hyprland host namespace is no longer SUPER",
    )
    require(
        'local main_mod = "ALT"' in guest_hypr,
        "guest namespace is not ALT",
    )
    require(
        'local main_mod = "SUPER"' not in guest_hypr,
        "guest regained host SUPER namespace",
    )

    require(
        "KEY_RIGHTCTRL" in looking_glass,
        "Looking Glass transport escape is not RightCtrl",
    )

    # The managed host configs must not allocate ALT as a global compositor
    # namespace. Guest ALT therefore remains disjoint even when a capture
    # transition occurs at an awkward time.
    for line in sway.splitlines():
        stripped = line.strip()
        if stripped.startswith(("bindsym ", "bindcode ")):
            key_side = stripped.split(" exec ", 1)[0]
            require(
                "Alt+" not in key_side
                and "+Alt" not in key_side,
                f"Sway host captured ALT namespace: {stripped}",
            )

    require(
        '" + ALT +' not in host_hypr
        and '"ALT"' not in host_hypr,
        "host Hyprland captured guest ALT namespace",
    )

    # Guest global compositor bindings must all pass through main_mod. This
    # specifically prevents bare media/function keys from overlapping host
    # bindings.
    guest_args = bind_first_arguments(guest_hypr)

    require(
        guest_args,
        "no guest compositor bindings were discovered",
    )

    for argument in guest_args:
        require(
            argument.strip().startswith("main_mod .."),
            (
                "guest binding escaped the ALT namespace: "
                f"{argument.strip()}"
            ),
        )

    for key in (
        "XF86AudioRaiseVolume",
        "XF86AudioLowerVolume",
        "XF86AudioMute",
        "XF86AudioPlay",
        "XF86AudioNext",
        "XF86AudioPrev",
    ):
        require(
            f'main_mod .. " + {key}"' in guest_hypr,
            f"guest media binding is not ALT-prefixed: {key}",
        )

    require(
        'main_mod .. " + SHIFT + T"' in guest_hypr,
        "guest theme binding did not move to ALT+SHIFT+T",
    )
    require(
        'main_mod .. " + SHIFT + W"' in guest_hypr,
        "guest wallpaper binding did not move to ALT+SHIFT+W",
    )
    require(
        'main_mod .. " + ALT + T"' not in guest_hypr
        and 'main_mod .. " + ALT + W"' not in guest_hypr,
        "guest contains duplicate ALT modifier chords",
    )

    # Guest desktop presentation/configuration may not acquire host control
    # plane knowledge. These tokens are intentionally checked only in the
    # guest-facing compositor template, not in Ansible cleanup metadata.
    forbidden_guest_tokens = (
        "hyperlabctl",
        "virsh",
        "libvirt",
        "vfio",
        "/sys/",
        "/etc/ly/",
        "privatestack-compositor-adapter",
        "privatestack-hyperlab-domains",
        "privatestack-session-lifecycle",
    )

    guest_lower = guest_hypr.lower()

    for token in forbidden_guest_tokens:
        require(
            token.lower() not in guest_lower,
            f"guest-facing source leaks host detail: {token}",
        )

    # Historical rejected fullscreen experiments must not silently return.
    for rejected in (
        "CTRL + ALT + F11",
        "CTRL + F11",
        '"F11"',
    ):
        require(
            rejected not in guest_hypr,
            f"rejected fullscreen experiment returned: {rejected}",
        )

    require(
        'main_mod .. " + F"' in guest_hypr,
        "guest local fullscreen binding disappeared",
    )

    print(
        "HyperLab host/guest keybinding namespace security contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
