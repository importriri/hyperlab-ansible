import QtQuick

// One delegate instance per model entry, each told its modelData.
Item {
    id: variants

    property var model: []
    default property Component delegate

    anchors.fill: parent

    Repeater {
        model: variants.model

        Loader {
            required property var modelData

            width: variants.width
            height: variants.height
            sourceComponent: variants.delegate
            onLoaded: item.modelData = modelData
        }
    }
}
