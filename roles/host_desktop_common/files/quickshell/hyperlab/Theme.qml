// HyperLab Platform theme boundary (V447-C9.3).
//
// The host-owned theme registry renders the semantic palette. This file only
// reads that reviewed artefact, validates it and exposes named roles to
// presentation files. It never derives trust from appearance and never
// writes theme state.
//
// Three separate systems meet here and stay separate:
//
//   appearance   palette roles: the charcoal foundation, its lifts, its
//                boundaries and its neutral focus tone
//   provenance   fixed identity colours reached only through
//                provenanceColor(); immutable across every appearance
//   status       semanticStatusColor(), used for text and shape, never as
//                ordinary chrome
//
// The fallback is deliberately neutral. A palette that cannot be read must
// not repaint the product in an arbitrary hue, so the unavailable-palette
// foundation is built numerically from greys rather than from a second
// hard-coded colour scheme.

import Quickshell
import Quickshell.Io
import QtQuick

Scope {
    id: theme

    // Neutral unavailable-palette foundation. Every value is a grey or a
    // status tone; nothing here carries product or provenance identity.
    readonly property var fallbackPalette: ({
        "name": "unavailable",
        "base": Qt.rgba(0.03, 0.035, 0.04, 1),
        "mantle": Qt.rgba(0.05, 0.055, 0.065, 1),
        "surface": Qt.rgba(0.08, 0.09, 0.10, 1),
        "overlay": Qt.rgba(0.13, 0.14, 0.16, 1),
        "text": Qt.rgba(0.94, 0.96, 0.98, 1),
        "subtext": Qt.rgba(0.60, 0.65, 0.70, 1),
        "accent": Qt.rgba(0.82, 0.84, 0.87, 1),
        "accent2": Qt.rgba(0.70, 0.73, 0.76, 1),
        "ok": "limegreen",
        "warn": "gold",
        "bad": "crimson"
    })

    property var palette: theme.fallbackPalette

    // True once a reviewed palette artefact has been read and validated.
    property bool paletteAvailable: false

    // Appearance roles. Every shell surface is opaque and one of these.
    readonly property color base: theme.palette.base
    readonly property color mantle: theme.palette.mantle
    readonly property color surface: theme.palette.surface
    readonly property color overlay: theme.palette.overlay
    readonly property color text: theme.palette.text
    readonly property color subtext: theme.palette.subtext
    readonly property color accent: theme.palette.accent

    readonly property string paletteName:
        String(theme.palette.name)

    readonly property bool trustModelActive:
        theme.paletteName === "trust-model"

    // Explicit text tones. A label picks one of these; it never stacks an
    // opacity on top of a muted colour.
    readonly property color textPrimary: theme.text
    readonly property color textSecondary: theme.subtext
    readonly property color textQuiet: theme.mix(theme.subtext, theme.surface, 0.72)
    readonly property color textDisabled: theme.mix(theme.subtext, theme.surface, 0.45)

    // Structure. Boundaries are explicit colours with real contrast against
    // the surface they sit on; hairlines separate, boundaries enclose.
    readonly property color hairline: theme.mix(theme.text, theme.surface, 0.10)
    readonly property color boundary: theme.mix(theme.text, theme.surface, 0.24)
    readonly property color boundaryStrong: theme.mix(theme.text, theme.surface, 0.40)
    readonly property color recess: theme.mix(theme.base, theme.overlay, 0.65)

    // Focus is neutral and identical everywhere. It is never a provenance
    // colour, because focus is not a security claim.
    readonly property color focusRing: theme.mix(theme.text, theme.surface, 0.62)

    // Interactive fills over any surface.
    readonly property color fillHover: theme.alpha(theme.text, 0.07)
    readonly property color fillPressed: theme.alpha(theme.text, 0.11)
    readonly property color fillSelected: theme.mix(theme.text, theme.surface, 0.16)
    readonly property color scrim: theme.alpha(theme.base, 0.62)

    // Chrome: opaque rail, opaque workspace, raised cards and panels.
    readonly property color rail: theme.mantle
    readonly property color workspace: theme.surface
    readonly property color raised: theme.overlay
    readonly property color floating: theme.surface

    // The reviewed provenance identities. HOST is the neutral control plane
    // and UNCLASSIFIED is the explicit absence of an identity; neither is a
    // trust domain, and neither takes part in the GPU handoff ladder.
    readonly property var provenanceIdentities: [
        "host",
        "clean",
        "dev",
        "services",
        "dirty",
        "lab"
    ]

    // Every identity the registry publishes is present and usable. When it is
    // not, provenance falls back to neutral text and Diagnostics can say so
    // instead of the shell quietly inventing an identity colour.
    readonly property bool provenanceAvailable: {
        for (let index = 0; index < theme.provenanceIdentities.length; index++) {
            const key = "dom_" + theme.provenanceIdentities[index];

            if (typeof theme.palette[key] !== "string")
                return false;
        }

        return true;
    }

    function alpha(candidate, level) {
        const source = Qt.color(candidate);

        return Qt.rgba(source.r, source.g, source.b, level);
    }

    // Opaque blend of two palette colours; weight is the share of `top`.
    function mix(top, bottom, weight) {
        const a = Qt.color(top);
        const b = Qt.color(bottom);

        return Qt.rgba(
            a.r * weight + b.r * (1 - weight),
            a.g * weight + b.g * (1 - weight),
            a.b * weight + b.b * (1 - weight),
            1
        );
    }

    function validPalette(candidate) {
        const required = [
            "name",
            "base",
            "mantle",
            "surface",
            "overlay",
            "text",
            "subtext",
            "accent",
            "accent2",
            "ok",
            "warn",
            "bad"
        ];

        for (let index = 0; index < required.length; index++) {
            const key = required[index];

            if (
                candidate[key] === undefined
                || typeof candidate[key] !== "string"
                || candidate[key].length === 0
            ) {
                return false;
            }
        }

        return true;
    }

    function applyPalette(raw) {
        const source = String(raw).trim();

        if (source.length === 0)
            return;

        try {
            const parsed = JSON.parse(source);

            if (!theme.validPalette(parsed))
                return;

            theme.palette = parsed;
            theme.paletteAvailable = true;
            console.info(
                "HyperLab palette loaded: " + parsed.name
            );
        } catch (error) {
            console.warn(
                "HyperLab semantic palette parse failed"
            );
        }
    }

    // Operational status. Used for text and shape only; ordinary controls
    // resolve to neutral, never to a trust identity.
    // Success is neutral. Several legacy palettes define `ok` as exactly a
    // canonical provenance hue (green's ok is CLEAN), so borrowing it would
    // make an ordinary "reporting" or "completed" read as a trust claim.
    // Only warning and failure carry a status colour, always beside text.
    function semanticStatusColor(statusClass) {
        switch (String(statusClass)) {
        case "ok":
            return theme.textPrimary;
        case "warning":
        case "warn":
            return theme.palette.warn;
        case "error":
        case "bad":
        case "critical":
            return theme.palette.bad;
        default:
            return theme.textPrimary;
        }
    }

    // Readouts stay primary text until the host reports a state worth a
    // colour; unavailable readouts are quiet, not zero.
    function telemetryTextColor(candidate) {
        const statusClass = String(candidate.class);

        if (statusClass === "unavailable" || statusClass === "unknown")
            return theme.textQuiet;

        if (statusClass.length === 0 || statusClass === "ok")
            return theme.textPrimary;

        return theme.semanticStatusColor(statusClass);
    }

    // Provenance only. The host owns the identity; the shell never infers one
    // from a window title, a wallpaper or a theme name. An identity outside
    // the reviewed set, and an unavailable identity table, both resolve to
    // neutral text rather than to a borrowed colour.
    function provenanceColor(identity) {
        const key = String(identity).toLowerCase();

        if (theme.provenanceIdentities.indexOf(key) < 0)
            return theme.textSecondary;

        const value = theme.palette["dom_" + key];

        if (typeof value !== "string")
            return theme.textSecondary;

        return value;
    }

    // The word an operator reads beside the marker. Tracked capitals are
    // reserved for provenance and short group labels.
    function provenanceLabel(identity) {
        const key = String(identity).toLowerCase();

        if (key === "unclassified" || key.length === 0)
            return "Unclassified";

        if (theme.provenanceIdentities.indexOf(key) < 0)
            return "Unknown";

        return key.charAt(0).toUpperCase() + key.slice(1);
    }

    function knownProvenance(identity) {
        return theme.provenanceIdentities.indexOf(
            String(identity).toLowerCase()
        ) >= 0;
    }

    // The worst state reported by any secondary readout, so the rail can
    // show one honest indicator instead of seven competing numbers.
    function worstStatusClass(payloads) {
        let worst = "";

        for (let index = 0; index < payloads.length; index++) {
            const statusClass =
                String(payloads[index].class);

            if (
                statusClass === "error"
                || statusClass === "bad"
                || statusClass === "critical"
            ) {
                return "bad";
            }

            if (
                statusClass === "warn"
                || statusClass === "warning"
            ) {
                worst = "warn";
            }
        }

        return worst;
    }

    function refreshPalette() {
        paletteFile.reload();
    }

    Component.onCompleted: {
        theme.applyPalette(
            paletteFile.text()
        );
    }

    FileView {
        id: paletteFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "palette-quickshell.json"

        blockLoading: true

        onTextChanged: {
            theme.applyPalette(
                this.text()
            );
        }
    }
}
