import QtQuick

// A layer-shell window as a plain item placed by its anchors. The harness
// renames `anchors { ... }` to `edges { ... }` in its staged copy.
Item {
    id: panel

    property PanelEdges edges: PanelEdges {}
    property PanelMargins margins: PanelMargins {}
    property var screen: null
    property color color: "transparent"
    property real exclusiveZone: 0
    property int exclusionMode: 0
    property var mask: null

    width: edges.left && edges.right ? parent.width : implicitWidth
    height: edges.top && edges.bottom ? parent.height : implicitHeight
    x: edges.left ? margins.left : (edges.right ? parent.width - width - margins.right : (parent.width - width) / 2)
    y: edges.top ? margins.top : (edges.bottom ? parent.height - height - margins.bottom : (parent.height - height) / 2)

    Rectangle {
        anchors.fill: parent
        color: panel.color
        z: -1
    }
}
