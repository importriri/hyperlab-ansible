// HyperLab host key sheet.
//
// The keys the host compositor binds, in the operator's words. The groups
// below are plain JSON between the markers so the host keybinding contract
// can compare them with the bindings in both directions: every host key is
// on the sheet, and the sheet promises no key that is not bound. Host keys
// only: guest keys (ALT) live on each guest's own sheet, ALT + H.

import QtQuick

QtObject {
    // HOST-KEYS-BEGIN
    readonly property var groups: [
        { "title": "HyperLab", "keys": [
            { "keys": "SUPER+SPACE", "does": "Command palette: destinations, Machines and host commands" },
            { "keys": "SUPER+F1", "does": "This key sheet" },
            { "keys": "SUPER+F4", "does": "Machines" },
            { "keys": "SUPER+X", "does": "Control Center" },
            { "keys": "SUPER+SHIFT+P", "does": "Control Center" },
            { "keys": "SUPER+F2", "does": "Diagnostics" },
            { "keys": "SUPER+F3", "does": "hyperlabctl doctor in a terminal" },
            { "keys": "SUPER+SHIFT+B", "does": "Show or hide the top rail" }
        ] },
        { "title": "Crossing to a Machine", "keys": [
            { "keys": "SUPER+SHIFT+V", "does": "Send the host clipboard text to one running Machine, chosen now" },
            { "keys": "Right CTRL", "does": "Release the keyboard and mouse from Looking Glass" }
        ] },
        { "title": "Windows", "keys": [
            { "keys": "SUPER+Return", "does": "Terminal" },
            { "keys": "SUPER+SHIFT+Return", "does": "Floating terminal" },
            { "keys": "SUPER+SHIFT+F", "does": "Files" },
            { "keys": "SUPER+D", "does": "Application launcher" },
            { "keys": "SUPER+H J K L", "does": "Focus left, down, up, right" },
            { "keys": "SUPER+SHIFT+H J K L", "does": "Move the window left, down, up, right" },
            { "keys": "SUPER+F", "does": "Fullscreen" },
            { "keys": "SUPER+SHIFT+SPACE", "does": "Float or tile" },
            { "keys": "SUPER+O", "does": "Window opacity" },
            { "keys": "SUPER+R", "does": "Resize with H J K L; Return or Escape ends" },
            { "keys": "SUPER+drag", "does": "Move (left button) or resize (right button)" },
            { "keys": "SUPER+SHIFT+Q", "does": "Close the window" }
        ] },
        { "title": "Workspaces", "keys": [
            { "keys": "SUPER+1 … 9", "does": "Go to workspace n" },
            { "keys": "SUPER+SHIFT+1 … 9", "does": "Send the window to workspace n" }
        ] },
        { "title": "Session and appearance", "keys": [
            { "keys": "SUPER+Escape", "does": "Lock the screen" },
            { "keys": "SUPER+SHIFT+Escape", "does": "Emergency stop: cut every running Machine's network, then pause it; Restore is in the shell" },
            { "keys": "SUPER+SHIFT+T", "does": "Next theme" },
            { "keys": "SUPER+SHIFT+W", "does": "Wallpaper mode" },
            { "keys": "SUPER+CTRL+Space", "does": "Next keyboard layout" },
            { "keys": "Print", "does": "Screenshot of the whole screen" },
            { "keys": "SHIFT+Print", "does": "Screenshot of a region" },
            { "keys": "CTRL+Print", "does": "Screenshot of a region, choosing where to save it" }
        ] }
    ]
    // HOST-KEYS-END
}
