import QtQuick
import Quickshell

QtObject {
    id: handler

    property string target: ""

    Component.onCompleted: {
        const map = Object.assign({}, QsHarness.ipc);
        map[target] = handler;
        QsHarness.ipc = map;
    }
}
