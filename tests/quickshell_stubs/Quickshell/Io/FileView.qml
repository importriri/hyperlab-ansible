import QtQuick
import Quickshell

// Reads QsHarness.files[path]; a path without a fixture fails to load. A
// list fixture answers its entries in turn and then keeps the last one.
QtObject {
    id: file

    property string path: ""
    property bool watchChanges: false
    property bool printErrors: true
    property bool blockLoading: false
    property string content: ""
    property int reads: 0

    signal loaded()
    signal loadFailed(int error)
    signal fileChanged()
    signal textChanged()

    function text() {
        return file.content;
    }

    function reload() {
        const value = QsHarness.files[file.path];
        if (value === undefined) {
            file.content = "";
            file.loadFailed(0);
            return;
        }
        if (Array.isArray(value)) {
            file.content = String(value[Math.min(file.reads, value.length - 1)]);
            file.reads += 1;
        } else {
            file.content = String(value);
        }
        file.textChanged();
        file.loaded();
    }

    onPathChanged: Qt.callLater(file.reload)
}
