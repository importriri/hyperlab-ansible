// Visual language of the HyperLab Workspace Shell.
//
// A workstation of the HyperLab platform, not a copy of the host: floating
// islands, IBM Plex, one accent. Colours follow the active guest theme
// through the palette the theme controller writes; the HyperLab Workstation
// palette is the built-in default, so a missing or unreadable palette still
// draws a coherent shell.
//
// The guest never shows trust. Nothing here encodes a trust level, a
// provenance colour or GPU ownership: only the host frame may say what this
// machine is.

import Quickshell
import Quickshell.Io
import QtQuick

Item {
    id: theme

    visible: false

    // Palette, as hex strings without '#', exactly as the controller writes.
    property var colours: ({
        "background": "05070b",
        "foreground": "e6ebf5",
        "surface": "0a0e16",
        "accent": "5b8cff",
        "accent_alt": "8fb0ff",
        "urgent": "ff5c7a"
    })
    property string paletteError: ""

    readonly property color background: hex(colours.background)
    readonly property color text: hex(colours.foreground)
    readonly property color accent: hex(colours.accent)
    readonly property color accentAlt: hex(colours.accent_alt)
    readonly property color urgent: hex(colours.urgent)
    readonly property color surface: hex(colours.surface)

    // Derived surfaces.
    readonly property color glass: alpha(surface, 0.88)
    readonly property color glassStrong: alpha(surface, 0.965)
    readonly property color scrim: alpha(background, 0.62)
    readonly property color scrimDeep: alpha(background, 0.9)
    readonly property color line: mix(surface, text, 0.14)
    readonly property color lineStrong: mix(surface, text, 0.24)
    readonly property color textMuted: mix(text, surface, 0.36)
    readonly property color textSoft: mix(text, surface, 0.16)
    readonly property color accentSoft: alpha(accent, 0.15)
    readonly property color accentGlow: alpha(accent, 0.35)
    readonly property color dotIdle: mix(surface, text, 0.32)
    readonly property color highlight: alpha(text, 0.05)

    // Type.
    readonly property string sans: "IBM Plex Sans"
    readonly property string mono: "IBM Plex Mono"

    // Geometry.
    readonly property int gap: 16
    readonly property int islandHeight: 44
    readonly property int radius: 14
    readonly property int radiusSmall: 10
    readonly property int dockHeight: 60

    // Motion.
    property bool reducedMotion: false
    readonly property int fast: reducedMotion ? 0 : 140
    readonly property int normal: reducedMotion ? 0 : 240
    readonly property int slow: reducedMotion ? 0 : 420

    function hex(value) {
        const clean = String(value || "").replace(/^#/, "");
        if (!/^[0-9a-fA-F]{6}$/.test(clean))
            return Qt.rgba(1, 0, 1, 1);
        return Qt.rgba(
            parseInt(clean.slice(0, 2), 16) / 255,
            parseInt(clean.slice(2, 4), 16) / 255,
            parseInt(clean.slice(4, 6), 16) / 255,
            1
        );
    }

    function alpha(colour, amount) {
        return Qt.rgba(colour.r, colour.g, colour.b, amount);
    }

    function mix(a, b, amount) {
        return Qt.rgba(
            a.r + (b.r - a.r) * amount,
            a.g + (b.g - a.g) * amount,
            a.b + (b.b - a.b) * amount,
            1
        );
    }

    // Accept a palette only when every key is a six-digit hex colour.
    function applyPalette(text) {
        if (String(text).trim().length === 0)
            return;
        let data;
        try {
            data = JSON.parse(String(text));
        } catch (error) {
            theme.paletteError = "The guest palette is not valid JSON.";
            return;
        }
        const keys = ["background", "foreground", "surface", "accent", "accent_alt", "urgent"];
        for (let i = 0; i < keys.length; i++) {
            if (!data || !/^[0-9a-fA-F]{6}$/.test(String(data[keys[i]] || ""))) {
                theme.paletteError = "The guest palette is missing " + keys[i] + ".";
                return;
            }
        }
        theme.paletteError = "";
        theme.colours = data;
    }

    FileView {
        id: paletteFile

        path: Quickshell.env("HOME") + "/.config/privatestack-guest/palette.json"
        watchChanges: true
        printErrors: false

        onFileChanged: reload()
        onTextChanged: theme.applyPalette(this.text())
    }
}
