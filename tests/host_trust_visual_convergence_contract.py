#!/usr/bin/env python3
"""C9 trust-model host visual convergence contract."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
QML = "roles/host_desktop_common/files/quickshell/hyperlab/"


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(
            "HyperLab host visual contract: " + message
        )


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]

    require(
        stage["design_system"] == "c9-platform",
        "visual contract is not the C9.3 HyperLab Platform system",
    )

    bar = text(QML + "HyperLabBar.qml")
    tokens = text(QML + "Tokens.qml")
    identity = text(QML + "IdentityMark.qml")
    gpu = text(QML + "GpuBadge.qml")
    panel = text(QML + "SystemPanel.qml")
    launcher = text(QML + "LauncherSurface.qml")
    context = text(QML + "ContextCluster.qml")

    require(
        "readonly property int barHeight: 37" in tokens
        and "implicitHeight: bar.tokens.barHeight" in bar
        and "exclusiveZone: bar.tokens.barHeight" in bar,
        "37px reserve changed",
    )

    for marker, corpus in (
        ("id: barChrome", bar),
        ('text: "HyperLab"', identity),
        # One circular product symbol, one wordmark, one subtitle.
        ("IsolationGlyph {", identity),
        ('text: "Platform"', identity),
        ("badge.claim.claimed", gpu),
        (
            "provenanceColor(badge.claim.identity)",
            gpu,
        ),
        ("id: centeredClock", context),
        ('title: "Keyboard"', panel),
        ('title: "Theme"', panel),
        ('title: "Wallpaper"', panel),
        ("launcher.icons.power", launcher),
    ):
        require(
            marker in corpus,
            "C9 presentation marker missing: " + marker,
        )

    # Trust colour is provenance only; generic controls remain theme-driven.
    for generic in (
        text(QML + "ShellControl.qml"),
        text(QML + "PanelRow.qml"),
        text(QML + "ShellCard.qml"),
        text(QML + "ShellLabel.qml"),
        text(QML + "WorkspaceFrame.qml"),
        text(QML + "WorkspaceStrip.qml"),
        text(QML + "EmptyState.qml"),
        text(QML + "SectionHeader.qml"),
    ):
        require(
            "provenanceColor(" not in generic,
            "generic chrome gained trust-colour authority",
        )

    require(
        "provenanceColor(" in gpu,
        "explicit provenance presentation disappeared",
    )

    # Focus is neutral everywhere: it is not a security claim.
    for corpus in (
        text(QML + "ShellControl.qml"),
        text(QML + "PanelRow.qml"),
        text(QML + "ShellCard.qml"),
    ):
        require(
            "theme.focusRing" in corpus,
            "a control stopped using the shared neutral focus ring",
        )

    # The product symbol is one geometry family, reused, not a second logo.
    for corpus in (
        text(QML + "IdentityMark.qml"),
        text(QML + "HyperLabDesktop.qml"),
        text(QML + "WorkspaceSurface.qml"),
    ):
        require(
            "IsolationGlyph {" in corpus,
            "a product surface lost the shared HyperLab symbol",
        )

    print(
        "HyperLab C9 host trust visual convergence contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
