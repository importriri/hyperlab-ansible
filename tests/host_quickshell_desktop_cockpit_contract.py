#!/usr/bin/env python3
"""C9.3 HyperLab Platform desktop truth and presentation-boundary contract."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab"

BRIDGE_OWNERS = {
    "ShellState.qml",
    "ShellActions.qml",
    "MachineActions.qml",
    "Theme.qml",
}
IPC_RECEIVERS = {"ShellIpc.qml"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    config = yaml.safe_load(
        (ROOT / "group_vars/all/host-desktop.yml").read_text(
            encoding="utf-8"
        )
    )
    shell_stage = config["host_desktop_common_shell_stage"]

    registered = shell_stage["surface_files"]

    require(
        set(registered) == {path.name for path in QML.glob("*.qml")},
        "unregistered or missing QML",
    )
    require(
        set(shell_stage["bridge_owner_files"]) == BRIDGE_OWNERS,
        "bridge owner set changed",
    )
    require(
        set(shell_stage["ipc_receiver_files"]) == IPC_RECEIVERS,
        "IPC receiver set changed",
    )
    require(
        shell_stage["design_system"] == "c9-platform",
        "HyperLab Platform design system changed",
    )
    require(
        shell_stage["desktop_surface_layer"] == "bottom",
        "desktop layer changed",
    )
    # The idle desktop takes no input at all: nothing is hidden behind it.
    require(
        shell_stage["desktop_surface_input"] == "none",
        "desktop input model changed",
    )
    require(
        shell_stage["workspace_surface_kind"] == "floating-window",
        "the product workspace stopped being an ordinary window",
    )
    require(
        shell_stage["workspace_destinations"]
        == ["machines", "controls", "diagnostics"],
        "product destination set changed",
    )

    desktop = (QML / "HyperLabDesktop.qml").read_text(
        encoding="utf-8"
    )
    workspace = (QML / "WorkspaceSurface.qml").read_text(
        encoding="utf-8"
    )
    module = (QML / "MachineModule.qml").read_text(
        encoding="utf-8"
    )
    stage = (QML / "MachineStage.qml").read_text(
        encoding="utf-8"
    )
    state = (QML / "ShellState.qml").read_text(
        encoding="utf-8"
    )
    gpu_badge = (QML / "GpuBadge.qml").read_text(
        encoding="utf-8"
    )
    tokens = (QML / "Tokens.qml").read_text(
        encoding="utf-8"
    )

    for marker in (
        "PanelWindow",
        "WlrLayer.Bottom",
        "WlrKeyboardFocus.None",
        "exclusiveZone: 0",
        # An empty input region: every click reaches the compositor.
        "mask: Region {}",
    ):
        require(
            marker in desktop,
            f"desktop foundation missing {marker}",
        )

    # The product workspace is a compositor-managed window, not a layer
    # surface disguised as an application.
    for marker in (
        "FloatingWindow",
        "minimumSize:",
        "visible: workspace.shellSurfaces.workspaceOpen",
        "ConfirmationSurface {",
    ):
        require(
            marker in workspace,
            f"product workspace foundation missing {marker}",
        )

    for forbidden in (
        "PanelWindow",
        "WlrLayershell",
    ):
        require(
            forbidden not in workspace,
            f"product workspace became a layer surface: {forbidden}",
        )

    require(
        "readonly property int barHeight: 37" in tokens,
        "bar reserve changed",
    )

    # Machine presentation remains a truthful host projection. It does not
    # acquire lifecycle or hypervisor authority.
    for marker in (
        "module.machine.provenance",
        "module.machine.state",
        "module.machine.gpu_relation",
        "module.machine.memory_mb",
        "module.machine.vcpus",
        "module.machine.networks",
        "module.machine.name",
        # Allocation is what the machine was given, never what it is using.
        'text: "Memory"',
        'text: "vCPU"',
    ):
        require(
            marker in module,
            f"machine module missing {marker}",
        )

    require(
        "signal activated()" in (QML / "ShellCard.qml").read_text(
            encoding="utf-8"
        ),
        "the shared card lost its activation signal",
    )

    for forbidden in (
        "Image {",
        "AnimatedImage",
        "ScreencopyView",
        "virsh",
        "shutdown(",
        "destroy(",
    ):
        require(
            forbidden not in module,
            f"machine module gained backend behavior: {forbidden}",
        )

    for marker in (
        "MachineModule {",
        "MachineListRow {",
        "machinesAvailable",
        "shellState",
        # Every machine stays reachable: no two-row cap, no self-referential
        # handoff tile, and a virtualized list for large inventories.
        "ListView {",
        "selectMachine(",
    ):
        require(
            marker in stage,
            f"machine stage missing {marker}",
        )

    for forbidden in (
        "visibleLimit",
        "hiddenCount",
        "View all in Machines",
    ):
        require(
            forbidden not in stage,
            f"inventory cap returned: {forbidden}",
        )

    # Trust is explicit host state; the shell never infers it from appearance.
    for marker in (
        "function applyTrustPayload(raw)",
        # Only an affirmative, schema-valid observation is accepted: the
        # backend's explicit `known`, a boolean claim, no error payload.
        "function validTrustObservation(parsed)",
        "parsed.known !== true",
        'typeof parsed.claimed !== "boolean"',
        # A boot claim is only accepted at that identity's canonical rung,
        # and SERVICES is outside the GPU handoff entirely.
        "readonly property var gpuLadder",
        "parsed.level !== rung",
        # Every renderer asks this before reading the claim.
        "readonly property string trustClaimState",
        "applyMachinePayload(this.text)",
        "parsed.machines_available !== true",
        "state.machines = []",
        "machinesWithProvenance",
        "function machineById(identifier)",
        "machinesGeneration",
        "function sourceState(declared, observedAt)",
        "degradedSources",
    ):
        require(
            marker in state,
            f"state missing {marker}",
        )

    require(
        "badge.claim.claimed" in gpu_badge
        and "provenanceColor(badge.claim.identity)" in gpu_badge,
        "rail trust summary stopped following explicit provenance",
    )

    actions = (QML / "ShellActions.qml").read_text(
        encoding="utf-8"
    )

    combined = []

    for path in QML.glob("*.qml"):
        source = path.read_text(encoding="utf-8")
        combined.append(source)

        for route in re.findall(r'invoke\("([^"]+)"\)', source):
            require(
                f'"{route}"' in actions,
                f"{path.name}: unreviewed route {route}",
            )

        for forbidden in (
            "hyprctl",
            "swaymsg",
            "sudo",
            "pkexec",
            "virsh",
            "virt-viewer",
            "looking-glass-client",
            "/sys/",
            "/proc/",
            "/bin/sh",
            "/bin/bash",
            "execDetached",
            "ShellCommand",
            "Quickshell.Hyprland",
            "Quickshell.I3",
            "DesktopEntries",
            "MouseArea",
        ):
            require(
                forbidden not in source,
                f"{path.name}: forbidden {forbidden}",
            )

        require(
            not re.search(r"#[0-9a-fA-F]{6}", source),
            f"{path.name}: QML palette literal",
        )

        if path.name not in BRIDGE_OWNERS:
            require(
                not re.search(
                    r"(?m)^[ \t]*(?:Process|FileView|Socket)[ \t]*\{",
                    source,
                ),
                f"{path.name}: presentation reads backend",
            )

        if path.name not in IPC_RECEIVERS:
            require(
                "IpcHandler" not in source,
                f"{path.name}: IPC receiver outside ShellIpc",
            )

    ipc = (QML / "ShellIpc.qml").read_text(
        encoding="utf-8"
    )

    require(
        "Process {" not in ipc
        and "shellActions.invoke" not in ipc,
        "IPC receiver may start or route backend actions",
    )

    require(
        config["host_desktop_common_product_contract"][
            "supported_compositors"
        ]
        == ["hyprland", "sway"],
        "recovery parity changed",
    )

    # Host projection remains truthful and deliberately small.
    spec = importlib.util.spec_from_file_location(
        "cockpit_render",
        ROOT / "tools/hyperlabctl/hyperlabctl/render.py",
    )
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)

    domains = [
        {
            "name": "clean-looking-name",
            "state": "unknown",
            "trust_profile": None,
            "network": "clean",
            "vfio": False,
        },
        {
            "name": "actual-dev",
            "state": "shut off",
            "trust_profile": "dev",
            "vfio": True,
            "memory_mb": 8192,
        },
        {
            "name": "actual-clean",
            "state": "running",
            "trust_profile": "clean",
            "vfio": True,
        },
    ]

    payload = render.waybar_field(
        {
            "domains": domains,
            "gpu": {"held_by": "actual-clean"},
        },
        "vms",
    )

    require(
        payload["text"] == "1/3"
        and payload["machines_available"],
        "machine summary changed",
    )

    rows = payload["machines"]

    require(
        [row["provenance"] for row in rows]
        == ["clean", "dev", "unclassified"],
        "trust inferred or machine order changed",
    )
    require(
        [row["gpu"] for row in rows]
        == [
            "GPU held",
            "Passthrough configured",
            "GPU assignment unknown",
        ],
        "GPU claim inflated",
    )
    require(
        rows[1]["state"] == "shut off"
        and rows[1]["memory_mb"] == 8192,
        "machine facts changed",
    )
    # The authoritative presentation projection. It carries the facts the
    # shell must show and the structured relation it must reason about, and
    # it deliberately carries no operation capability: capability depends on
    # the live spec registry and runtime SSH inventory, which the reviewed
    # machine bridge owns.
    require(
        set(rows[0])
        == {
            "name",
            "state",
            "provenance",
            "gpu",
            "gpu_relation",
            "memory_mb",
            "vcpus",
            "network",
            "networks",
            "managed",
            "vfio",
            "lifecycle",
            "device_profile",
            "blocked",
        },
        "machine projection leaked extra data",
    )

    for capability in ("capabilities", "verbs", "can_start", "actions"):
        require(
            capability not in rows[0],
            f"presentation projection claimed capability: {capability}",
        )

    require(
        [row["gpu_relation"] for row in rows]
        == ["held", "configured", "unknown"],
        "structured GPU relation changed",
    )

    # An unread domain has unknown networks; a domain with no interface has
    # none. Collapsing them is how "None" starts meaning "we did not look".
    unknown_networks = render.machine_cards(
        {
            "domains": [
                {
                    "name": "opaque",
                    "state": "unknown",
                    "trust_profile": None,
                    "networks": None,
                }
            ]
        }
    )[0]

    require(
        unknown_networks["networks"] is None
        and unknown_networks["network"] is None,
        "unknown networks collapsed into none",
    )

    for missing in ({}, {"domains": None}):
        result = render.waybar_field(missing, "vms")
        require(
            not result["machines_available"]
            and result["machines"] == []
            and result["class"] == "error"
            and result["text"] == "?",
            "failure looks empty or healthy",
        )

    empty = render.waybar_field({"domains": []}, "vms")
    require(
        empty["machines_available"]
        and empty["machines"] == [],
        "empty inventory looks failed",
    )

    for profile in ("services", "dirty", "lab", "bogus"):
        row = render.machine_cards(
            {
                "domains": [
                    {
                        "name": "vm",
                        "state": "paused",
                        "trust_profile": profile,
                    }
                ]
            }
        )[0]

        require(
            row["provenance"]
            == (
                profile
                if profile != "bogus"
                else "unclassified"
            ),
            "profile validation changed",
        )
        require(
            row["state"] == "paused",
            "non-running state collapsed",
        )

    claim = render.waybar_field(
        {
            "trust": {
                "claimed": True,
                "name": "dev",
                "level": 2,
            }
        },
        "trust",
    )

    require(
        claim["claimed"] is True
        and claim["identity"] == "dev"
        and claim["level"] == 2,
        "claim projection changed",
    )

    bogus = render.waybar_field(
        {
            "trust": {
                "claimed": True,
                "name": "root",
                "level": 9,
            }
        },
        "trust",
    )

    require(
        bogus["claimed"] is False
        and bogus["identity"] is None
        and bogus["level"] is None,
        "unknown identity accepted as claim",
    )

    unclaimed = render.waybar_field(
        {"trust": {"claimed": False}},
        "trust",
    )

    require(
        unclaimed["claimed"] is False
        and unclaimed["text"] == "unclaimed",
        "unclaimed projection changed",
    )

    print("HyperLab C9.3 HyperLab Platform desktop contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
