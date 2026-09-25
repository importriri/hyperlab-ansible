// HyperLab workspace frame (V447-C9.3).
//
// One page shape for Machines, the Control Center and Diagnostics: a single
// heading, an optional trailing slot, section navigation and a scrollable
// body. Because every destination uses it, a view never restates the product
// name, never invents its own heading treatment and never places an action
// where the page below the fold can hide it.
//
// The frame is responsive by capacity, not by monitor: wide layouts get a
// section sidebar, narrow layouts get a row of section chips, and the body
// always scrolls before any essential type shrinks.

import QtQuick

Item {
    id: frame

    required property var tokens
    required property var theme

    property string title: ""
    property string subtitle: ""
    property string subtitleClass: ""

    // [{ "id": "session", "label": "Session" }]
    property var sections: []
    property string currentSection: ""

    // A settings or explanation page is a column of prose and rows: past a
    // certain measure it stops being readable and starts being a spreadsheet.
    // Zero means the body may use the whole viewport, which is what an
    // inventory grid wants.
    property int maxContentWidth: 0

    property alias trailing: trailingRow.data
    default property alias content: bodyHolder.data

    readonly property bool compact:
        frame.width < frame.tokens.breakpointMedium

    readonly property bool sectioned: frame.sections.length > 1

    readonly property int padding:
        frame.compact
        ? frame.tokens.workspacePaddingCompact
        : frame.tokens.workspacePadding

    readonly property int bodyWidth: bodyHolder.width

    signal sectionRequested(string identifier)

    Column {
        anchors.fill: parent
        spacing: 0

        // Heading.
        Item {
            width: parent.width
            height: frame.tokens.workspaceHeaderHeight

            Row {
                id: headingRow

                anchors.left: parent.left
                anchors.right: trailingRow.left
                anchors.leftMargin: frame.padding
                anchors.rightMargin: frame.tokens.spaceMd
                anchors.verticalCenter: parent.verticalCenter
                spacing: frame.tokens.spaceMd

                ShellLabel {
                    anchors.verticalCenter: parent.verticalCenter
                    tokens: frame.tokens
                    role: "display"
                    text: frame.title
                    color: frame.theme.textPrimary

                    Accessible.role: Accessible.Heading
                }

                ShellLabel {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: 2
                    visible: !frame.compact && text.length > 0
                    tokens: frame.tokens
                    role: "body"
                    text: frame.subtitle
                    color:
                        frame.subtitleClass.length > 0
                        ? frame.theme.semanticStatusColor(frame.subtitleClass)
                        : frame.theme.textSecondary
                }
            }

            Row {
                id: trailingRow

                anchors.right: parent.right
                anchors.rightMargin: frame.padding
                anchors.verticalCenter: parent.verticalCenter
                spacing: frame.tokens.spaceSm
            }
        }

        Rectangle {
            width: parent.width
            height: 1
            color: frame.theme.hairline
        }

        // Section navigation and body.
        Item {
            width: parent.width
            height: parent.height - frame.tokens.workspaceHeaderHeight - 1

            // Narrow layouts carry sections as a chip row above the body.
            Flickable {
                id: chipStrip

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: frame.padding
                anchors.rightMargin: frame.padding
                anchors.topMargin: frame.sectioned && frame.compact
                    ? frame.tokens.spaceMd
                    : 0

                visible: frame.sectioned && frame.compact
                height: visible ? frame.tokens.controlHeight : 0
                contentWidth: chipRow.implicitWidth
                contentHeight: height
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true

                Row {
                    id: chipRow

                    spacing: frame.tokens.spaceXs

                    Repeater {
                        model: frame.sections

                        delegate: ShellControl {
                            required property var modelData

                            objectName: "chip-" + modelData.id
                            tokens: frame.tokens
                            theme: frame.theme
                            flat: true
                            selected: modelData.id === frame.currentSection
                            accessibleName: modelData.label

                            content: [
                                ShellLabel {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: frame.tokens
                                    role: "body"
                                    text: modelData.label
                                    color:
                                        modelData.id === frame.currentSection
                                        ? frame.theme.textPrimary
                                        : frame.theme.textSecondary
                                }
                            ]

                            onActivated: frame.sectionRequested(modelData.id)
                        }
                    }
                }
            }

            // Wide layouts carry sections as a bounded sidebar.
            Column {
                id: sidebar

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.topMargin: frame.padding
                anchors.leftMargin: frame.tokens.spaceMd

                visible: frame.sectioned && !frame.compact
                width: visible ? frame.tokens.navigationWidth : 0
                spacing: 2

                Repeater {
                    model: frame.sections

                    delegate: PanelRow {
                        id: sectionRow

                        required property var modelData

                        objectName: "section-" + modelData.id
                        width: parent.width
                        height: frame.tokens.rowHeightCompact
                        tokens: frame.tokens
                        theme: frame.theme
                        title: modelData.label
                        interactive: true
                        current: modelData.id === frame.currentSection

                        onActivated: frame.sectionRequested(modelData.id)

                        // The open section is marked, not only tinted: a
                        // neutral fill alone is easy to miss.
                        Rectangle {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            visible: sectionRow.current
                            width: 2
                            height: parent.height - frame.tokens.spaceMd
                            radius: 1
                            color: frame.theme.textPrimary
                        }
                    }
                }
            }

            // Tab never lands on something scrolled out of sight.
            FocusFollow {
                flickable: viewport
            }

            FocusFollow {
                flickable: chipStrip
            }

            Flickable {
                id: viewport

                anchors.top: chipStrip.visible ? chipStrip.bottom : parent.top
                anchors.topMargin: frame.padding
                anchors.left: sidebar.visible ? sidebar.right : parent.left
                anchors.leftMargin: frame.padding
                anchors.right: parent.right
                anchors.rightMargin: frame.padding
                anchors.bottom: parent.bottom
                anchors.bottomMargin: frame.padding

                contentWidth: width
                contentHeight: bodyHolder.childrenRect.height
                interactive: contentHeight > height
                boundsBehavior: Flickable.StopAtBounds
                clip: true

                Item {
                    id: bodyHolder

                    width:
                        frame.maxContentWidth > 0
                        ? Math.min(viewport.width, frame.maxContentWidth)
                        : viewport.width
                    height: childrenRect.height
                }
            }

            // A scrollable region says so: a thin neutral indicator, visible
            // only while there is more page than viewport.
            Rectangle {
                anchors.right: parent.right
                anchors.rightMargin: 2

                visible: viewport.interactive
                width: 2
                radius: 1
                color: frame.theme.boundaryStrong
                opacity: 0.8

                height:
                    viewport.height
                    * (viewport.height / Math.max(1, viewport.contentHeight))

                y:
                    viewport.y
                    + viewport.contentY
                    / Math.max(1, viewport.contentHeight)
                    * viewport.height
            }
        }
    }
}
