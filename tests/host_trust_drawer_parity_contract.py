#!/usr/bin/env python3
"""C9.2 native diagnostics and trust-routing contract."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

QML = ROOT / (
    "roles/host_desktop_common/files/"
    "quickshell/hyperlab"
)

BRIDGE = ROOT / (
    "roles/host_desktop_common/files/"
    "privatestack-shell-actions.py"
)

LEGACY_ACTIONS = {
    "vms-drawer-open",
    "diagnostics-drawer-open",
    "vms-control-center-open",
    "diagnostics-control-center-open",
}


def mapping(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)

    raise SystemExit(name + " missing")


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    actions = mapping(BRIDGE, "ACTIONS")

    require(
        LEGACY_ACTIONS.isdisjoint(actions),
        "legacy diagnostics route re-entered shell actions",
    )

    config = yaml.safe_load(
        (ROOT / "group_vars/all/host-desktop.yml").read_text(
            encoding="utf-8"
        )
    )

    stage = config["host_desktop_common_shell_stage"]

    require(
        "DiagnosticsView.qml" in stage["surface_files"],
        "native diagnostics view is not registered",
    )

    require(
        "machine-inspector" not in stage["summoned_surfaces"],
        "detached machine inspector returned",
    )

    surfaces = (QML / "ShellSurfaces.qml").read_text(
        encoding="utf-8"
    )
    desktop = (QML / "HyperLabDesktop.qml").read_text(
        encoding="utf-8"
    )
    workspace = (QML / "WorkspaceSurface.qml").read_text(
        encoding="utf-8"
    )
    diagnostics = (QML / "DiagnosticsView.qml").read_text(
        encoding="utf-8"
    )

    require(
        '"diagnostics"' in surfaces,
        "native diagnostics workspace route is missing",
    )

    require(
        "DiagnosticsView {" in workspace,
        "native diagnostics view is not mounted in the product workspace",
    )

    # The idle desktop is not a diagnostics surface. Trust, ownership and
    # machine content belong to the workspace an operator opens.
    for forbidden in (
        "DiagnosticsView {",
        "OwnershipInstrument {",
        "MachineStage {",
        "ControlCenterView {",
        "HostFooter {",
    ):
        require(
            forbidden not in desktop,
            f"idle desktop became a permanent dashboard: {forbidden}",
        )

    require(
        "Trust" in diagnostics or "trust" in diagnostics,
        "native diagnostics view lost trust presentation",
    )

    # Ownership, boot claim and focused provenance stay separable questions.
    for marker in (
        "OwnershipInstrument {",
        "Resolved provenance",
        "Current owner",
        "Boot claim",
    ):
        require(
            marker in diagnostics or marker in (
                QML / "OwnershipInstrument.qml"
            ).read_text(encoding="utf-8"),
            f"diagnostics lost an ownership distinction: {marker}",
        )

    print(
        "HyperLab C9.2 native diagnostics/trust routing contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
