// HyperLab command surface (V447-C9.3).
//
// A keyboard-first palette over the whole shell: type to filter, arrows to
// move, Return to act, Escape to leave. Results are grouped the way an
// operator thinks about them:
//
//   Destinations  the three native product workspaces
//   Machines      the live inventory, opened and selected by identifier
//   Commands      the reviewed typed host actions, each showing its current
//                 state and where it executes
//
// Dispatch is explicit per kind: a destination goes to ShellSurfaces, a
// machine selects an identifier, and only a reviewed command reaches the
// action bridge. An alias such as "workstation controls" resolves to the one
// destination it means instead of producing a duplicate row.
//
// The surface builds no command line and reaches nothing the action bridge
// does not already allow; the query never leaves the shell. Applications are
// deliberately absent: launching arbitrary desktop entries from shared QML
// would be an execution primitive outside the typed bridge.
//
// One launcher answers at a time, on the output that summoned it.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: launcher

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellActions
    required property var shellSurfaces

    property var modelData

    screen: modelData

    readonly property string outputName:
        launcher.screen ? String(launcher.screen.name) : ""

    readonly property bool open:
        launcher.shellSurfaces.launcherOpen
        && launcher.shellSurfaces.ownsTransient("launcher", launcher.outputName)

    property string query: ""
    property int cursor: 0

    // Native destinations. Aliases resolve to the destination they name, so
    // "workstation controls" and "power" reach the Control Center without
    // becoming rows of their own.
    readonly property var destinations: [
        { title: "Machines", hint: "Inventory and machine operations",
          glyph: launcher.icons.machines, workspace: "machines", page: "",
          aliases: "vm virtual machines guests inventory" },
        { title: "Control Center", hint: "Host settings and session controls",
          glyph: launcher.icons.controlCenter, workspace: "controls",
          page: "session",
          aliases: "workstation controls power session lock settings" },
        { title: "Diagnostics", hint: "Trust, isolation and runtime health",
          glyph: launcher.icons.diagnostics, workspace: "diagnostics",
          page: "overview",
          aliases: "health sources observations problems" },
        { title: "Isolation and GPU", hint: "Ownership, boot claim and policy",
          glyph: launcher.icons.isolation, workspace: "diagnostics",
          page: "isolation", aliases: "gpu vfio passthrough trust ladder" }
    ]

    // The reviewed command catalogue. Section, hint and context are
    // presentation; action is the only thing that leaves the shell.
    readonly property var commands: [
        { title: "Cycle theme",
          hint: "Current  " + launcher.shellState.themeLabel(),
          context: "host appearance",
          glyph: launcher.icons.theme, action: "theme-cycle", osd: "theme" },
        { title: "Cycle wallpaper mode",
          hint: "Current  " + launcher.shellState.wallpaperLabel(),
          context: "host appearance",
          glyph: launcher.icons.wallpaper,
          action: "wallpaper-mode-toggle", osd: "wallpaper" },
        { title: "Cycle keyboard layout",
          hint: "Current  " + launcher.shellState.keyboardName(),
          context: "host input",
          glyph: launcher.icons.keyboard,
          action: "keyboard-cycle", osd: "keyboard" },
        { title: "Mute or unmute",
          hint: "Audio  " + String(launcher.shellState.audioPayload.text),
          context: "host audio",
          glyph: launcher.icons.audioMuted,
          action: "audio-mute-toggle", osd: "audio" },
        { title: "Volume up", hint: "+5", context: "host audio",
          glyph: launcher.icons.audio,
          action: "audio-volume-up", osd: "audio" },
        { title: "Volume down", hint: "−5", context: "host audio",
          glyph: launcher.icons.audio,
          action: "audio-volume-down", osd: "audio" },
        { title: "Lock the screen", hint: "Immediate", context: "host session",
          glyph: launcher.icons.power, action: "session-lock", osd: "" }
    ]

    function acronym(text) {
        return String(text)
            .split(/\s+/)
            .map(word => word.charAt(0))
            .join("")
            .toLowerCase();
    }

    function matchesQuery(text, needle) {
        const haystack = String(text).toLowerCase();

        return haystack.indexOf(needle) >= 0
            || launcher.acronym(text).indexOf(needle) === 0;
    }

    // Flat result list with section rows. An empty query favours navigation
    // and reviewed commands; machines appear once an operator asks for them,
    // so opening the palette never lists two hundred rows before the three
    // destinations.
    readonly property var results: {
        const needle = launcher.query.trim().toLowerCase();
        const out = [];

        const destinations = launcher.destinations.filter(entry =>
            needle.length === 0
            || launcher.matchesQuery(entry.title, needle)
            || entry.aliases.indexOf(needle) >= 0
        );

        if (destinations.length > 0) {
            out.push({ kind: "section", title: "Destinations" });

            for (const entry of destinations)
                out.push({ kind: "destination", entry: entry });
        }

        if (needle.length > 0) {
            const machines = launcher.shellState.machines.filter(machine =>
                launcher.matchesQuery(machine.name, needle)
                || String(machine.provenance).indexOf(needle) >= 0
                || String(machine.state).indexOf(needle) >= 0
            );

            if (machines.length > 0) {
                out.push({ kind: "section", title: "Machines" });

                for (const machine of machines)
                    out.push({ kind: "machine", machine: machine });
            }
        }

        const commands = launcher.commands.filter(entry =>
            needle.length === 0
            || launcher.matchesQuery(entry.title, needle)
            || entry.context.indexOf(needle) >= 0
        );

        if (commands.length > 0) {
            out.push({ kind: "section", title: "Commands" });

            for (const entry of commands)
                out.push({ kind: "command", entry: entry });
        }

        return out;
    }

    readonly property var selectable: {
        const indices = [];

        for (let index = 0; index < launcher.results.length; index++) {
            if (launcher.results[index].kind !== "section")
                indices.push(index);
        }

        return indices;
    }

    // Keep the bounded result viewport aligned to whole rows. A clipped
    // half-row looks like content has slipped under the footer; scrolling
    // remains available, but the resting viewport always ends cleanly.
    readonly property int resultSpacing: 2

    readonly property real resultViewportHeight: {
        let total = 0;

        for (let index = 0; index < launcher.results.length; index++) {
            const result = launcher.results[index];
            const rowHeight =
                result.kind === "section"
                ? launcher.tokens.fontLabel + launcher.tokens.spaceMd
                : launcher.tokens.launcherRowHeight;
            const spacing =
                index === 0 ? 0 : launcher.resultSpacing;
            const candidate = total + spacing + rowHeight;

            if (candidate > launcher.tokens.launcherListMax)
                break;

            total = candidate;
        }

        return total;
    }

    onResultsChanged: launcher.cursor = 0

    onOpenChanged: {
        if (launcher.open) {
            launcher.query = "";
            launcher.cursor = 0;
            queryInput.text = "";
            queryInput.forceActiveFocus();
        }
    }

    function moveCursor(delta) {
        if (launcher.selectable.length === 0)
            return;

        launcher.cursor =
            (launcher.cursor + delta + launcher.selectable.length)
            % launcher.selectable.length;

        resultList.positionViewAtIndex(
            launcher.selectable[launcher.cursor],
            ListView.Contain
        );
    }

    // Dispatch is per kind. A destination never travels through the action
    // bridge, and the action bridge never receives anything but a reviewed
    // identifier.
    function activate(position) {
        if (position < 0 || position >= launcher.selectable.length)
            return;

        const result = launcher.results[launcher.selectable[position]];

        launcher.shellSurfaces.closeLauncher();

        if (result.kind === "destination") {
            launcher.shellSurfaces.openWorkspacePage(
                result.entry.workspace,
                result.entry.page
            );
            return;
        }

        if (result.kind === "machine") {
            launcher.shellSurfaces.selectMachine(
                String(result.machine.name),
                launcher.shellState.machinesGeneration
            );
            return;
        }

        const accepted = launcher.shellActions.invoke(result.entry.action);

        if (result.entry.osd.length > 0) {
            launcher.shellSurfaces.showActionOsd(
                result.entry.osd,
                result.entry.action,
                accepted,
                launcher.outputName
            );
        }
    }

    visible: launcher.open

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusiveZone: 0
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "hyperlab-launcher"
    WlrLayershell.keyboardFocus:
        launcher.open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    // Click outside closes.
    TapHandler {
        onTapped: launcher.shellSurfaces.closeLauncher()
    }

    Rectangle {
        id: card

        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.round(parent.height * launcher.tokens.launcherTop)

        width: Math.min(
            launcher.tokens.launcherWidth,
            parent.width - launcher.tokens.spaceHuge * 2
        )

        height: Math.min(
            column.implicitHeight + launcher.tokens.panelPadding * 2,
            parent.height - y - launcher.tokens.spaceHuge
        )

        radius: launcher.tokens.radiusSurface
        color: launcher.theme.floating
        border.width: launcher.tokens.borderSize
        border.color: launcher.theme.boundary
        clip: true

        opacity: launcher.open ? 1 : 0

        Accessible.role: Accessible.Dialog
        Accessible.name: "HyperLab command surface"

        Behavior on opacity {
            NumberAnimation {
                duration:
                    launcher.open
                    ? launcher.tokens.motionEnter
                    : launcher.tokens.motionExit
                easing.type: Easing.OutCubic
            }
        }

        TapHandler {
            onTapped: {}
        }

        Column {
            id: column

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: launcher.tokens.panelPadding
            spacing: launcher.tokens.spaceMd

            // Query field.
            Rectangle {
                width: parent.width
                height: launcher.tokens.launcherFieldHeight
                radius: launcher.tokens.radiusControl
                color: launcher.theme.raised
                border.width:
                    queryInput.activeFocus
                    ? launcher.tokens.focusOutline
                    : launcher.tokens.borderSize
                border.color:
                    queryInput.activeFocus
                    ? launcher.theme.focusRing
                    : launcher.theme.boundary

                Row {
                    anchors.fill: parent
                    anchors.leftMargin: launcher.tokens.spaceLg
                    anchors.rightMargin: launcher.tokens.spaceLg
                    spacing: launcher.tokens.spaceMd

                    ShellIcon {
                        anchors.verticalCenter: parent.verticalCenter
                        tokens: launcher.tokens
                        grid: "control"
                        text: launcher.icons.launcher
                        color: launcher.theme.textSecondary
                    }

                    TextInput {
                        id: queryInput

                        focus: true
                        anchors.verticalCenter: parent.verticalCenter
                        width:
                            parent.width
                            - launcher.tokens.iconControl
                            - launcher.tokens.spaceMd

                        font.family: launcher.tokens.fontSans
                        font.pixelSize: launcher.tokens.fontHeading
                        font.weight: Font.Normal
                        color: launcher.theme.textPrimary
                        selectionColor: launcher.theme.fillSelected
                        selectedTextColor: launcher.theme.textPrimary
                        clip: true

                        Accessible.role: Accessible.EditableText
                        Accessible.name: "Search machines and commands"

                        onTextChanged: launcher.query = text

                        Keys.onEscapePressed:
                            launcher.shellSurfaces.closeLauncher()
                        Keys.onDownPressed: launcher.moveCursor(1)
                        Keys.onUpPressed: launcher.moveCursor(-1)
                        Keys.onTabPressed: launcher.moveCursor(1)
                        Keys.onReturnPressed: launcher.activate(launcher.cursor)
                        Keys.onEnterPressed: launcher.activate(launcher.cursor)

                        ShellLabel {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: queryInput.text.length === 0
                            tokens: launcher.tokens
                            role: "heading"
                            font.weight: Font.Normal
                            text: "Search machines and commands"
                            color: launcher.theme.textQuiet
                        }
                    }
                }
            }

            // Results. Virtualized, so a long inventory stays reachable and
            // the selected row is always scrolled into view.
            ListView {
                id: resultList

                width: parent.width
                height: Math.min(
                    contentHeight,
                    launcher.resultViewportHeight
                )

                model: launcher.results
                currentIndex:
                    launcher.selectable.length > 0
                    ? launcher.selectable[launcher.cursor]
                    : -1
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                interactive: contentHeight > height
                cacheBuffer: launcher.tokens.launcherRowHeight * 6
                spacing: launcher.resultSpacing

                delegate: Item {
                    id: resultRow

                    required property var modelData

                    // The launcher result model is a tagged union:
                    // section | machine | destination | command.
                    // Normalize that boundary once so bindings never
                    // dereference a member which does not belong to the
                    // current variant, including during delegate lifecycle.
                    readonly property var rowData:
                        modelData === undefined || modelData === null
                        ? ({})
                        : modelData

                    readonly property string kind:
                        resultRow.rowData.kind === undefined
                        ? ""
                        : String(resultRow.rowData.kind)

                    readonly property var entry:
                        resultRow.rowData.entry === undefined
                        || resultRow.rowData.entry === null
                        ? ({})
                        : resultRow.rowData.entry

                    readonly property var machine:
                        resultRow.rowData.machine === undefined
                        || resultRow.rowData.machine === null
                        ? ({})
                        : resultRow.rowData.machine

                    readonly property string sectionTitle:
                        resultRow.rowData.title === undefined
                        ? ""
                        : String(resultRow.rowData.title)
                    required property int index

                    readonly property bool isSection:
                        resultRow.kind === "section"
                    readonly property int position:
                        launcher.selectable.indexOf(index)
                    readonly property bool current:
                        !isSection && position === launcher.cursor

                    width: ListView.view.width
                    height:
                        isSection
                        ? launcher.tokens.fontLabel + launcher.tokens.spaceMd
                        : launcher.tokens.launcherRowHeight

                    ShellLabel {
                        visible: resultRow.isSection
                        anchors.left: parent.left
                        anchors.leftMargin: launcher.tokens.spaceMd
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        tokens: launcher.tokens
                        role: "label"
                        text: resultRow.isSection ? resultRow.sectionTitle : ""
                        color: launcher.theme.textSecondary
                    }

                    Rectangle {
                        visible: !resultRow.isSection
                        anchors.fill: parent
                        radius: launcher.tokens.radiusControl
                        color:
                            resultRow.current
                            ? launcher.theme.fillSelected
                            : (rowHover.hovered
                                ? launcher.theme.fillHover
                                : "transparent")
                        border.width:
                            resultRow.current
                            ? launcher.tokens.focusOutline
                            : 0
                        border.color: launcher.theme.focusRing

                        Accessible.role: Accessible.Button
                        Accessible.name: {
                            if (resultRow.kind === "machine")
                                return String(resultRow.machine.name);

                            if (resultRow.kind === "section")
                                return "";

                            return String(resultRow.entry.title);
                        }

                        Behavior on color {
                            ColorAnimation {
                                duration: launcher.tokens.motionHover
                            }
                        }

                        // Machine result.
                        Row {
                            visible: resultRow.kind === "machine"
                            anchors.left: parent.left
                            anchors.leftMargin: launcher.tokens.spaceMd
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: launcher.tokens.spaceMd

                            ShellIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: launcher.tokens
                                grid: "control"
                                text: launcher.icons.machines
                                color: launcher.theme.textSecondary
                            }

                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(120, card.width * 0.32)
                                tokens: launcher.tokens
                                role: "body"
                                font.weight: Font.Medium
                                text:
                                    resultRow.kind === "machine"
                                    ? String(resultRow.machine.name)
                                    : ""
                                color: launcher.theme.textPrimary
                            }

                            ProvenanceTag {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: launcher.tokens
                                theme: launcher.theme
                                identity:
                                    resultRow.kind === "machine"
                                    ? String(resultRow.machine.provenance)
                                    : "unclassified"
                            }

                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: launcher.tokens
                                role: "meta"
                                text:
                                    resultRow.kind === "machine"
                                    ? launcher.icons.machineStateWord(
                                        resultRow.machine.state
                                      )
                                    : ""
                                color: launcher.theme.textSecondary
                            }
                        }

                        // Destination and command results share one row shape.
                        Row {
                            visible:
                                resultRow.kind === "command"
                                || resultRow.kind === "destination"
                            anchors.left: parent.left
                            anchors.leftMargin: launcher.tokens.spaceMd
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: launcher.tokens.spaceMd

                            ShellIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: launcher.tokens
                                grid: "control"
                                text:
                                    resultRow.kind === "section"
                                    ? ""
                                    : String(resultRow.entry.glyph)
                                color: launcher.theme.textSecondary
                            }

                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: launcher.tokens
                                role: "body"
                                font.weight: Font.Medium
                                text:
                                    resultRow.kind === "section"
                                    ? ""
                                    : String(resultRow.entry.title)
                                color: launcher.theme.textPrimary
                            }

                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: launcher.tokens
                                role: "meta"
                                text:
                                    resultRow.kind === "section"
                                    ? ""
                                    : String(resultRow.entry.hint)
                                color: launcher.theme.textSecondary
                            }
                        }

                        // Where it goes, always visible before it runs.
                        ShellLabel {
                            anchors.right: parent.right
                            anchors.rightMargin: launcher.tokens.spaceMd
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: launcher.tokens
                            role: "meta"
                            text: {
                                switch (resultRow.kind) {
                                case "machine":
                                    return "open";
                                case "destination":
                                    return "workspace";
                                case "command":
                                    return String(resultRow.entry.context);
                                default:
                                    return "";
                                }
                            }
                            color: launcher.theme.textQuiet
                        }

                        HoverHandler {
                            id: rowHover
                            onHoveredChanged: {
                                if (hovered && resultRow.position >= 0)
                                    launcher.cursor = resultRow.position;
                            }
                        }

                        TapHandler {
                            onTapped: launcher.activate(resultRow.position)
                        }
                    }
                }
            }

            EmptyState {
                width: parent.width
                visible: launcher.selectable.length === 0
                tokens: launcher.tokens
                theme: launcher.theme
                kind: "filtered"
                title: "Nothing matches"
                description:
                    "No destination, machine or reviewed command matches "
                    + "this search."
            }

            ShellLabel {
                tokens: launcher.tokens
                role: "meta"
                text: "↑↓ move · return open · esc close"
                color: launcher.theme.textQuiet
            }
        }
    }
}
