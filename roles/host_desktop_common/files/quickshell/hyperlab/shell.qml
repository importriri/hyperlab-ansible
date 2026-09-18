//@ pragma ShellId hyperlab

import Quickshell
import QtQuick

ShellRoot {
    Variants {
        model: Quickshell.screens

        HyperLabBar {
            required property var modelData
            screen: modelData
        }
    }
}
