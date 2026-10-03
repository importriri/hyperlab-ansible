pragma Singleton
import QtQuick

QtObject {
    property QtObject defaultAudioSink: QtObject {
        property QtObject audio: QtObject {
            property real volume: 0.65
            property bool muted: false
        }
    }
}
