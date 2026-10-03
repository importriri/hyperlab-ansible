pragma Singleton
import QtQuick

QtObject {
    property var screens: [{ "name": "HEADLESS-0", "width": 1920, "height": 1080 }]

    function env(name) {
        if (name === "HOME")
            return "/home/test";
        return name === "USER" ? "sid" : "";
    }

    function execDetached(argv) {
        QsHarness.record(argv);
    }

    function iconPath(name, check) {
        return "";
    }
}
