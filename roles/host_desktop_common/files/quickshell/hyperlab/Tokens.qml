// HyperLab Platform design tokens (V447-C9.3).
//
// One geometry, typography and motion scale for every HyperLab surface: the
// rail, the passive desktop, the product workspace, the launcher, the panels
// and the OSD. Compositor composition values are repeated here for alignment
// only; the composition contract keeps them in step with
// host_desktop_composition.
//
// Tokens carry no colour. Colour belongs to the reviewed theme registry and
// reaches the shell through Theme.qml. Provenance colours are never tokens.
//
// Every value is a logical unit. Physical acceptance at each supported scale
// is a runtime gate, not an assumption made here.

import QtQuick

QtObject {
    id: tokens

    // Top rail reserve. The physical 37px acceptance is part of the shell
    // contract and is not a free design value.
    readonly property int barHeight: 37

    // Spacing scale.
    readonly property int spaceXs: 4
    readonly property int spaceSm: 8
    readonly property int spaceMd: 12
    readonly property int spaceLg: 16
    readonly property int spaceXl: 20
    readonly property int spaceXxl: 24
    readonly property int spaceHuge: 32
    readonly property int spaceSection: 48

    // Radius scale. radiusWindow mirrors the compositor rounding so shell
    // surfaces and tiled windows read as one product; cards use the tighter
    // radiusCard.
    readonly property int radiusControl: 8
    readonly property int radiusWindow: 10
    readonly property int radiusSurface: 12
    readonly property int radiusCard: 6

    // Compositor composition, repeated for shell-side alignment only.
    readonly property int gapInner: 8
    readonly property int gapOuter: 16
    readonly property int borderSize: 1

    // Control geometry.
    readonly property int controlHeight: 28
    readonly property int controlHeightLarge: 32
    readonly property int controlPadding: 10
    readonly property int rowHeight: 40
    readonly property int rowHeightCompact: 32
    readonly property int dividerHeight: 16
    readonly property int markerSize: 8
    readonly property int iconBar: 16
    readonly property int iconControl: 20
    readonly property int iconProminent: 24
    readonly property int focusOutline: 2

    // Rail. 24px workspace slots; 18px brand mark; bounded side regions so a
    // long context string can never push the clock off centre.
    readonly property int workspaceSlot: 24
    readonly property int workspaceOverflow: 28
    readonly property int brandMark: 18
    readonly property int railRegionMin: 120
    readonly property int railClockGuard: 24

    // Product workspace host. One ordinary compositor-managed window shared
    // by Machines, Control Center and Diagnostics.
    readonly property int workspaceWidth: 1280
    readonly property int workspaceHeight: 820
    readonly property int workspaceMinWidth: 560
    readonly property int workspaceMinHeight: 380
    readonly property int workspacePadding: 24
    readonly property int workspacePaddingCompact: 16
    readonly property int workspaceHeaderHeight: 56
    readonly property int navigationWidth: 184
    readonly property int navigationWidthCompact: 56

    // Responsive breakpoints, expressed in available content width. They name
    // layout capacity, never a monitor model.
    readonly property int breakpointWide: 1600
    readonly property int breakpointMedium: 1100
    readonly property int breakpointNarrow: 760
    readonly property int breakpointShortHeight: 640

    // Machine inventory.
    readonly property int cardMinWidth: 300
    readonly property int cardMaxWidth: 420
    readonly property int cardHeight: 176
    readonly property int cardHeightCompact: 148
    readonly property int cardGap: 16
    readonly property int cardPadding: 16
    readonly property int listRowHeight: 56
    readonly property int contextPaneWide: 420
    readonly property int contextPaneCompact: 360

    // Explanatory instruments.
    readonly property int ownershipWidth: 440
    readonly property int policyCellGap: 8
    readonly property int policyCellHeight: 76
    readonly property int policyCellHeightCompact: 60
    readonly property int socketWidth: 28
    readonly property int socketHeight: 16
    readonly property int footerHeight: 32

    // Summoned surfaces.
    readonly property int launcherWidth: 680
    readonly property real launcherTop: 0.2
    readonly property int launcherFieldHeight: 56
    readonly property int launcherRowHeight: 48
    readonly property int launcherListMax: 420
    readonly property int panelWidth: 400
    readonly property int panelPadding: 20
    readonly property int dialogWidth: 460
    readonly property int osdWidth: 320
    readonly property int osdHeight: 72
    readonly property int osdBottom: 72

    // Typography. Two families with distinct jobs: the sans carries
    // navigation, names, headings and prose; the mono carries identifiers,
    // technical values and shortcuts. Nerd glyphs ride in the mono family.
    // Nothing essential renders below 13px; labels are 12px medium.
    readonly property string fontSans: "Adwaita Sans"
    readonly property string fontMono: "JetBrainsMono Nerd Font"
    readonly property string fontFamily: tokens.fontMono
    readonly property int fontLabel: 12
    readonly property int fontMeta: 13
    readonly property int fontBody: 14
    readonly property int fontValue: 16
    readonly property int fontHeading: 18
    readonly property int fontTitle: 20
    readonly property int fontDisplay: 24
    readonly property real trackingLabel: 0.6

    // Motion. Short, easing-out, explains location and state; no ambient
    // loops, no overshoot, no fabricated intermediate values. reducedMotion
    // is a real setting: the host publishes it and every animation reads it.
    property bool reducedMotion: false

    readonly property int motionHover: tokens.reducedMotion ? 0 : 100
    readonly property int motionWorkspace: tokens.reducedMotion ? 0 : 140
    readonly property int motionEnter: tokens.reducedMotion ? 0 : 160
    readonly property int motionExit: tokens.reducedMotion ? 0 : 120
    readonly property int motionExpand: tokens.reducedMotion ? 0 : 180
    readonly property int motionOsd: tokens.reducedMotion ? 0 : 100
    readonly property int motionReveal: tokens.reducedMotion ? 0 : 6
    readonly property int osdHoldMs: 1400
}
