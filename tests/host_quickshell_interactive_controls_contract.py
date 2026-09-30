#!/usr/bin/env python3
"""Contract for typed interactive controls in the shared HyperLab Shell."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

# Every presentation file that may carry pointer interaction: the registered
# surface set minus the root, the bridge owners and the coordinators.
NON_PRESENTATION = {
    "shell.qml",
    "Tokens.qml",
    "Icons.qml",
    "Theme.qml",
    "ShellState.qml",
    "ShellActions.qml",
    "MachineActions.qml",
    "ShellSurfaces.qml",
    "ShellIpc.qml",
}

# Reviewed C9.3 pointer topology. Activation lives in the three shared
# primitives -- ShellControl, PanelRow and ShellCard -- so a raw pointer
# handler anywhere else is a deliberate, named exception.
EXPECTED_TAP_HANDLERS = {
    # The three activation primitives.
    "ShellControl.qml": 1,
    "PanelRow.qml": 1,
    "ShellCard.qml": 1,
    # The identity mark carries the documented alternate-button shortcuts.
    "IdentityMark.qml": 1,
    # Compositor workspace chips.
    "WorkspaceStrip.qml": 1,
    # The dense machine list row.
    "MachineListRow.qml": 1,
    # Dismiss-on-outside-click surfaces, plus the card that swallows its own
    # taps so the dismiss handler does not fire underneath it.
    "ConfirmationSurface.qml": 1,
    "SystemPanel.qml": 2,
    "LauncherSurface.qml": 3,
}


EXPECTED_ACTIONS = [
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
]


EXPECTED_COMMANDS = {
    "keyboard-cycle": (
        "/usr/local/bin/privatestack-keyboard",
        "cycle",
    ),
    "wallpaper-mode-toggle": (
        "/usr/local/bin/privatestack-theme",
        "mode-toggle",
    ),
    "rgb-mode-toggle": (
        "/usr/local/bin/privatestack-theme",
        "rgb-mode-toggle",
    ),
    "theme-cycle": (
        "/usr/local/bin/privatestack-theme",
        "cycle",
    ),
    # Argument-free: the adapter identifies the workspace window by its
    # owning shell process, never by a value from presentation.
    "workspace-window-focus": (
        "/usr/local/bin/privatestack-compositor-adapter",
        "shell-window-focus",
    ),
    "session-lock": (
        "/usr/local/bin/privatestack-lock",
    ),
    "session-suspend": (
        "/usr/bin/systemctl",
        "suspend",
    ),
    "session-logout": (
        "/usr/local/bin/privatestack-compositor-adapter",
        "session-exit",
    ),
    "session-reboot": (
        "/usr/bin/systemctl",
        "reboot",
    ),
    "session-poweroff": (
        "/usr/bin/systemctl",
        "poweroff",
    ),
    "audio-mute-toggle": (
        "/usr/bin/wpctl",
        "set-mute",
        "@DEFAULT_AUDIO_SINK@",
        "toggle",
    ),
    "audio-volume-up": (
        "/usr/bin/wpctl",
        "set-volume",
        "-l",
        "1.25",
        "@DEFAULT_AUDIO_SINK@",
        "5%+",
    ),
    "audio-volume-down": (
        "/usr/bin/wpctl",
        "set-volume",
        "@DEFAULT_AUDIO_SINK@",
        "5%-",
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab interactive shell contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def parsed_actions(helper: str) -> dict[str, tuple[str, ...]]:
    tree = ast.parse(helper)

    for node in tree.body:
        value = None

        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ACTIONS"
        ):
            value = node.value
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name)
                and target.id == "ACTIONS"
                for target in node.targets
            ):
                value = node.value

        if value is not None:
            parsed = ast.literal_eval(value)

            require(
                isinstance(parsed, dict),
                "typed action bridge ACTIONS is not a dictionary",
            )

            return parsed

    raise SystemExit(
        "HyperLab interactive shell contract: "
        "typed action bridge ACTIONS mapping missing"
    )


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]
    product = shared["host_desktop_common_product_contract"]

    require(
        product["shell"]["fake_controls_allowed"] is False,
        "fake controls became allowed",
    )
    require(
        stage["session_controls_enabled"] is True,
        "interactive session control gate is disabled",
    )
    require(
        stage["session_action_bridge"]
        == "/usr/local/bin/privatestack-shell-actions",
        "typed action bridge changed",
    )
    require(
        stage["session_state_transport"] == "file-watch",
        "session state stopped being event-driven",
    )
    require(
        stage["session_actions"] == EXPECTED_ACTIONS,
        "typed session action allowlist changed",
    )

    shell_actions = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/ShellActions.qml"
    )
    shell_state = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/ShellState.qml"
    )
    presentation_files = [
        name for name in stage["surface_files"]
        if name not in NON_PRESENTATION
    ]

    presentation = "\n".join(
        text(
            "roles/host_desktop_common/files/"
            "quickshell/hyperlab/" + name
        )
        for name in presentation_files
    )
    shared_qml = "\n".join(
        (presentation, shell_actions, shell_state)
    )

    helper_path = (
        ROOT
        / "roles/host_desktop_common/files/"
        "privatestack-shell-actions.py"
    )
    helper = helper_path.read_text(encoding="utf-8")

    require(
        parsed_actions(helper) == EXPECTED_COMMANDS,
        "fixed typed command mapping changed",
    )

    # Focused-window operations act on ambient compositor focus, not on a
    # captured target, so the shell cannot request them at all; they live on
    # the compositor shortcuts until a target-bound operation is reviewed.
    for ambient in ("window-fullscreen-toggle", "window-opacity-toggle"):
        require(
            f'"{ambient}"' not in helper and f'"{ambient}"' not in shared_qml,
            f"ambient-focus action is reachable from the shell again: {ambient}",
        )

    tasks = text(
        "roles/host_desktop_common/tasks/main.yml"
    )

    require(
        '"/usr/local/bin/privatestack-shell-actions"' in shell_actions,
        "ShellActions lost the typed action bridge",
    )

    for action in EXPECTED_ACTIONS:
        marker = f'"{action}"'
        require(
            marker in shell_actions,
            f"typed action missing from ShellActions: {marker}",
        )
        require(
            marker in presentation,
            f"presentation action wiring missing: {marker}",
        )

    for marker in (
        "keyboardStateFile",
        "wallpaperModeStateFile",
        '"keyboard-layout"',
        '"wallpaper-mode"',
    ):
        require(
            marker in shell_state,
            f"session state marker missing: {marker}",
        )

    for marker in (
        'title: "Keyboard"',
        'title: "Theme"',
        'title: "Wallpaper"',
        'text: "HyperLab"',
        "badge.claim.claimed",
        "toggleLauncher(",
        "toggleSystemPanel(",
        # Feedback for a shell-requested host action is correlated with that
        # action, so an unrelated result can never settle it.
        "showActionOsd(",
        '"audio-volume-up"',
        "Qt.LeftButton",
        "Qt.RightButton",
        "Qt.MiddleButton",
        "WheelHandler {",
        "Keys.onEscapePressed",
        "Keys.onReturnPressed",
        # Destructive host actions reach the one shared confirmation, never
        # a local armed boolean.
        "requestConfirmation({",
        "submitConfirmation()",
        # Machine operation availability comes from the reviewed bridge, as
        # an observation ShellState correlates and validates.
        "pane.shellState.capabilityFor(",
        "machineActions.probe(",
    ):
        require(
            marker in presentation,
            f"interactive QML marker missing: {marker}",
        )

    # One capability model: presentation never reads a second, unvalidated
    # copy held by the transport layer.
    require(
        "machineActions.capability(" not in presentation
        and "machineActions.capabilityVerbs" not in presentation,
        "presentation reads capabilities from the transport layer",
    )

    for name in presentation_files:
        count = text(
            "roles/host_desktop_common/files/"
            "quickshell/hyperlab/" + name
        ).count("TapHandler {")
        require(
            count == EXPECTED_TAP_HANDLERS.get(name, 0),
            f"reviewed tap handler topology changed: {name} has {count}",
        )

    # Activation is a shared primitive, not a per-file habit: every control
    # is reachable by keyboard and announces itself.
    for name in ("ShellControl.qml", "PanelRow.qml", "ShellCard.qml"):
        primitive = text(
            "roles/host_desktop_common/files/"
            "quickshell/hyperlab/" + name
        )

        for marker in (
            "activeFocusOnTab:",
            "Keys.onPressed:",
            "Qt.Key_Return",
            "Qt.Key_Space",
            "Accessible.role:",
            "Accessible.name:",
        ):
            require(
                marker in primitive,
                f"{name} is not a real keyboard control: {marker}",
            )

    require(
        presentation.count("WheelHandler {") == 1,
        "C8 presentation must expose exactly one reviewed wheel handler",
    )

    # The command surface offers reviewed actions only, and no text it
    # collects ever becomes a command line.
    launcher = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/LauncherSurface.qml"
    )
    for action in re.findall(r'action: "([^"]+)"', launcher):
        require(
            action in EXPECTED_ACTIONS,
            f"launcher offers an unreviewed action: {action}",
        )
    require(
        "launcher.shellActions.invoke(result.entry.action);" in launcher
        and "query" in launcher
        and not re.search(
            r"shellActions\.invoke\([^)]*query",
            launcher,
        ),
        "launcher query leaks toward the action bridge",
    )

    # Every launcher result kind has its own dispatch. A destination never
    # travels through the action bridge with an empty action identifier.
    for marker in (
        'if (result.kind === "destination")',
        "shellSurfaces.openWorkspacePage(",
        'if (result.kind === "machine")',
        "shellSurfaces.selectMachine(",
    ):
        require(
            marker in launcher,
            f"launcher dispatch is not kind-aware: {marker}",
        )

    machine_stage = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/MachineStage.qml"
    )

    require(
        machine_stage.count(
            "stage.shellState.machinesGeneration,\n"
            "                                            false"
        ) == 1
        and machine_stage.count(
            "stage.shellState.machinesGeneration,\n"
            "                                    false"
        ) == 1,
        "machine-card selection may refocus the visible workspace",
    )

    require(
        'action: ""' not in launcher,
        "a launcher entry still routes an empty action to the bridge",
    )

    for forbidden in (
        "/usr/local/bin/privatestack-keyboard",
        "/usr/local/bin/privatestack-theme",
        "/usr/local/bin/privatestack-controls",
        "/usr/local/bin/privatestack-hyperlab-domains",
        "/usr/bin/wpctl",
        "hyprctl",
        "swaymsg",
        "sudo",
        "pkexec",
        "/bin/sh",
        '["sh", "-c"',
        '["bash", "-c"',
        "execDetached",
        "Quickshell.execDetached",
        "MouseArea",
    ):
        require(
            forbidden not in shared_qml,
            f"QML bypassed the typed action bridge: {forbidden}",
        )

    for action in EXPECTED_ACTIONS:
        marker = f'"{action}"'
        require(
            marker in helper,
            f"typed bridge marker missing: {marker}",
        )

    for marker in (
        '"/usr/local/bin/privatestack-keyboard"',
        '"/usr/local/bin/privatestack-theme"',
        '"/usr/local/bin/privatestack-compositor-adapter"',
        '"/usr/local/bin/privatestack-lock"',
        '"/usr/bin/systemctl"',
        '"/usr/bin/wpctl"',
        "trusted_target",
        "metadata.st_uid == 0",
        "metadata.st_mode & 0o022 == 0",
        "os.execv",
    ):
        require(
            marker in helper,
            f"typed bridge marker missing: {marker}",
        )

    for forbidden in (
        "controls-open",
        "/usr/local/bin/privatestack-controls",
        "privatestack-hyperlab-route",
        "subprocess",
        "os.system",
        "shell=True",
        "/bin/sh",
        "sudo",
        "pkexec",
        "hyprctl",
        "swaymsg",
        "virsh",
        "ansible-playbook",
    ):
        require(
            forbidden not in helper,
            f"typed bridge gained forbidden behavior: {forbidden}",
        )

    require(
        bool(helper_path.stat().st_mode & 0o111),
        "typed action bridge source is not executable",
    )

    for marker in (
        "Install the typed shared shell action bridge",
        "src: privatestack-shell-actions.py",
        "dest: /usr/local/bin/privatestack-shell-actions",
        'mode: "0755"',
    ):
        require(
            marker in tasks,
            f"action bridge deployment marker missing: {marker}",
        )

    roadmap = text("docs/roadmap.md")

    require(
        "- [x] reviewed interactive HyperLab controls" in roadmap,
        "interactive HyperLab milestone is not closed",
    )
    require(
        "- [x] HyperLab / trust / VM / audio action routing"
        in roadmap,
        "remaining interactive routing milestone is not closed",
    )

    print(
        "HyperLab shared interactive session controls contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
