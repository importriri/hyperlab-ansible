#!/usr/bin/env python3
"""Contract for the non-active shared HyperLab Quickshell foundation."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab shared shell contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )

    product = shared["host_desktop_common_product_contract"]
    stage = shared["host_desktop_common_shell_stage"]

    require(
        product["supported_compositors"]
        == ["hyprland", "sway"],
        "shared shell lost one supported compositor",
    )
    require(
        product["shell"]["primary"] == "quickshell",
        "Quickshell is not the product shell target",
    )
    require(
        product["shell"]["scope"] == "shared",
        "shell became compositor-specific",
    )

    expected_stage = {
        "implementation": "quickshell",
        "config_name": "hyperlab",
        "config_root": "/etc/xdg/quickshell/hyperlab",
        "package": "quickshell",
        "reviewed_api_series": "0.3",
        "runtime_enabled": False,
        "replacement_enabled": False,
        "waybar_fallback_required": True,
        "gtk_surface_fallback_required": True,
        "compositor_specific_imports_allowed": False,
        "read_only_runtime_data_enabled": True,
        "read_only_status_bridge": "/usr/local/bin/privatestack-hyperlab",
        "trust_update_transport": "event-stream",
        "slow_poll_seconds": 30,
        "workspace_state_enabled": True,
        "workspace_state_bridge": "/usr/local/bin/privatestack-compositor-adapter",
        "workspace_update_transport": "event-stream",
        "surface_provenance_bridge": (
            "/usr/local/bin/privatestack-surface-provenance"
        ),
        "surface_provenance_transport": "correlated-stream",
        "focus_accent_enabled": True,
        "focus_accent_bridge": "/usr/local/bin/privatestack-focus-accent",
        "focus_accent_unit": "hyperlab-focus-accent.service",
        "keyboard_rgb_modes": ["off", "system-trust", "focus-trust"],
        "keyboard_rgb_default_mode": "off",
        "semantic_palette_enabled": True,
        "semantic_palette_user_path": ".config/hyperlab/palette-quickshell.json",
        "telemetry_enabled": True,
        "telemetry_bridge": "/usr/local/bin/privatestack-telemetry",
        "telemetry_poll_seconds": 30,
        "telemetry_fields": [
            "temperature",
            "network",
            "audio",
            "battery",
        ],
        "session_controls_enabled": True,
        "session_action_bridge": "/usr/local/bin/privatestack-shell-actions",
        "session_state_transport": "file-watch",
        "session_actions": [
            "keyboard-cycle",
            "wallpaper-mode-toggle",
            "rgb-mode-toggle",
            "theme-cycle",
            "workspace-window-focus",
            "session-lock",
            "session-suspend",
            "session-logout",
            "session-reboot",
            "session-poweroff",
            "audio-mute-toggle",
            "audio-volume-up",
            "audio-volume-down",
        ],
        "design_system": "c9-platform",
        "surface_files": [
            "shell.qml",
            "Tokens.qml",
            "Theme.qml",
            "Icons.qml",
            "ShellState.qml",
            "ShellActions.qml",
            "MachineActions.qml",
            "ShellSurfaces.qml",
            "ShellIpc.qml",
            "ShellLabel.qml",
            "ShellIcon.qml",
            "ShellControl.qml",
            "ShellDivider.qml",
            "ShellCard.qml",
            "PanelRow.qml",
            "FocusFollow.qml",
            "SectionHeader.qml",
            "EmptyState.qml",
            "DashedFrame.qml",
            "IsolationGlyph.qml",
            "ProvenanceMarker.qml",
            "ProvenanceTag.qml",
            "StateChip.qml",
            "HardwareSocket.qml",
            "PolicyCell.qml",
            "ResourceMeter.qml",
            "ActionFeedback.qml",
            "OperationTracker.qml",
            "ConfirmationSurface.qml",
            "HyperLabBar.qml",
            "IdentityMark.qml",
            "WorkspaceStrip.qml",
            "ContextCluster.qml",
            "ProvenanceBadge.qml",
            "GpuBadge.qml",
            "SystemCluster.qml",
            "ControlEntry.qml",
            "HyperLabDesktop.qml",
            "WorkspaceSurface.qml",
            "WorkspaceFrame.qml",
            "MachineStage.qml",
            "MachineModule.qml",
            "MachineListRow.qml",
            "MachineContextPane.qml",
            "ControlCenterView.qml",
            "DiagnosticsView.qml",
            "OwnershipInstrument.qml",
            "HostFooter.qml",
            "SystemPanel.qml",
            "OsdSurface.qml",
            "LauncherSurface.qml",
        ],
        "bridge_owner_files": [
            "ShellState.qml",
            "ShellActions.qml",
            "MachineActions.qml",
            "Theme.qml",
        ],
        "ipc_receiver_files": ["ShellIpc.qml"],
        "ipc_targets": [
            "launcher",
            "appearance",
            "osd",
            "panel",
            "workspace",
            "bar",
        ],
        "summoned_surfaces": [
            "launcher",
            "system-panel",
            "osd",
        ],
        "workspace_surface_kind": "floating-window",
        "workspace_destinations": [
            "machines",
            "controls",
            "diagnostics",
        ],
        "desktop_surface_enabled": True,
        "desktop_surface_layer": "bottom",
        "desktop_surface_input": "none",
        "machine_action_bridge":
            "/usr/local/bin/privatestack-machine-actions",
        "machine_capability_source": "bridge",
        "machine_verbs": [
            "start",
            "shutdown",
            "reboot",
            "console",
            "ssh",
            "looking-glass",
            "force-stop",
        ],
        "machine_destructive_verbs": ["force-stop"],
        "parameterized_actions": ["workspace-select"],
        "product_navigation": {
            "hyprland": "quickshell",
            "sway": "recovery",
        },
    }

    for key, expected in expected_stage.items():
        require(
            key in stage and stage[key] == expected,
            f"shared shell stage invariant changed: {key}",
        )

    shell = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/shell.qml"
    )
    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
    )
    tokens = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/Tokens.qml"
    )
    state = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/ShellState.qml"
    )
    identity = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/IdentityMark.qml"
    )
    trust = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/GpuBadge.qml"
    )
    context = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/ContextCluster.qml"
    )
    tasks = text(
        "roles/host_desktop_common/tasks/main.yml"
    )

    for marker in (
        "//@ pragma ShellId hyperlab",
        "import Quickshell",
        "ShellRoot",
        "Variants",
        "model: Quickshell.screens",
        "HyperLabBar",
    ):
        require(
            marker in shell,
            f"root shell marker missing: {marker}",
        )

    for marker in (
        "id: sharedTokens",
        "id: sharedIcons",
        "id: sharedTheme",
        "id: sharedState",
        "id: sharedSurfaces",
        "id: sharedActions",
        "tokens: sharedTokens",
        "icons: sharedIcons",
        "theme: sharedTheme",
        "shellState: sharedState",
        "shellActions: sharedActions",
        "shellSurfaces: sharedSurfaces",
        "sharedState.settleAction(action)",
        "ShellIpc {",
        "MachineActions {",
        "machineActions: sharedMachineActions",
        "HyperLabDesktop {",
        "WorkspaceSurface {",
        "SystemPanel {",
        "OsdSurface {",
        "LauncherSurface {",
        # Operation results are observed once, at the root, and published
        # into the state layer rather than inferred by any view.
        "onActionResult:",
        "onSettled:",
        "sharedState.recordOperation(",
        "reducedMotion: sharedState.reducedMotion",
    ):
        require(
            marker in shell,
            f"shared dependency injection marker missing: {marker}",
        )

    for forbidden in (
        "id: tokens",
        "id: theme",
        "id: state",
        "id: actions",
        "tokens: tokens",
        "theme: theme",
        "shellState: state",
        "shellActions: actions",
        "state.settleAction(action)",
    ):
        require(
            forbidden not in shell,
            f"ambiguous QML self-binding returned: {forbidden}",
        )

    # Dependency injection is explicit. Component additions are reviewed by
    # name instead of a brittle global binding count.
    for marker in (
        "theme: sharedTheme",
        "shellState: sharedState",
        "shellSurfaces: sharedSurfaces",
        "tokens: sharedTokens",
        "icons: sharedIcons",
    ):
        require(
            marker in shell,
            f"shared dependency injection missing: {marker}",
        )


    for marker in (
        "PanelWindow",
        "implicitHeight: bar.tokens.barHeight",
        "exclusiveZone: bar.tokens.barHeight",
        "top: true",
        "left: true",
        "right: true",
    ):
        require(
            marker in bar,
            f"shared bar foundation marker missing: {marker}",
        )

    require(
        "readonly property int barHeight: 37" in tokens,
        "37px shared shell reserve changed",
    )
    require(
        'text: "HyperLab"' in identity,
        "HyperLab identity marker moved unexpectedly",
    )
    require(
        "claim" in trust
        and "provenanceColor(" in trust
        and "claimed" in trust,
        "trust badge no longer follows the explicit host claim",
    )
    require(
        "id: centeredClock" in context
        and "SystemClock {" in state
        and "import Quickshell.Io" in state,
        "clock/runtime ownership changed",
    )

    require(
        "property var modelData" in bar,
        "Variants delegate lost its modelData injection property",
    )

    # The rail performs no machine operation, so it is never handed the
    # machine action layer. This is the exact wiring defect C9.2 shipped.
    require(
        "machineActions" not in bar,
        "the rail regained machine operation authority",
    )
    require(
        "required property var modelData" not in bar,
        (
            "Quickshell 0.3 runtime-incompatible required modelData "
            "contract returned"
        ),
    )

    combined = "\n".join(
        text(
            "roles/host_desktop_common/files/"
            "quickshell/hyperlab/" + name
        )
        for name in stage["surface_files"]
    )

    for forbidden in (
        "Quickshell.Hyprland",
        "Quickshell.I3",
        "hyprctl",
        "swaymsg",
        "execDetached",
        "MouseArea",
        "ShellCommand",
        "DesktopEntries",
        '["sh", "-c"',
    ):
        require(
            forbidden not in combined,
            f"Phase 2A gained forbidden behavior: {forbidden}",
        )

    for marker in (
        "Install the reviewed shared Quickshell runtime",
        "Verify the reviewed Quickshell API series",
        "Create the shared HyperLab Quickshell config directory",
        "Install the non-active shared HyperLab Quickshell source",
        "Preserve recovery surfaces while the shared role stages Quickshell",
        "community.general.pacman:",
        "/etc/xdg/quickshell/hyperlab",
    ):
        require(
            marker in tasks,
            f"common role deployment marker missing: {marker}",
        )

    for forbidden in (
        "systemctl --user enable quickshell",
        "systemctl --user start quickshell",
        "qs -c hyperlab",
        "quickshell -c hyperlab",
    ):
        require(
            forbidden not in tasks,
            f"non-active stage gained runtime activation: {forbidden}",
        )

    require(
        not list(
            (
                ROOT / "roles/host_desktop_hyprland"
            ).rglob("*.qml")
        ),
        "shared QML leaked into the Hyprland-specific role",
    )

    require(
        not list(
            (
                ROOT / "roles/host_desktop_sway"
            ).rglob("*.qml")
        ),
        "shared QML leaked into the Sway-specific role",
    )

    print(
        "HyperLab shared Quickshell C9 contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
