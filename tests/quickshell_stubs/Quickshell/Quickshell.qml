pragma Singleton
import QtQuick

QtObject {
    property var screens: [{ "name": "HEADLESS-0", "width": 1920, "height": 1080 }]

    function env(name) {
        return name === "HOME" ? "/home/test" : "";
    }

    function execDetached(argv) {
        QsHarness.record(argv);
    }

    function iconPath(name, check) {
        return "";
    }
}
