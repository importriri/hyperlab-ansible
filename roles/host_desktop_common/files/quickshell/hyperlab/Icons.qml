// HyperLab icon language (V447-C9).
//
// One outline family (Material Design glyphs carried by the installed Nerd
// Font) referenced by role, so a surface never hard-codes a code point and
// the set stays small enough to read as a language. Hardware ownership is a
// hardware icon, never a shield: a shield would imply a security assessment
// the shell has not made. Provenance markers are shapes, not icons, and
// never double as state.

import QtQuick

QtObject {
    id: icons

    function glyph(codePoint) {
        return String.fromCodePoint(codePoint);
    }

    // Product surfaces.
    readonly property string machines: icons.glyph(0xF0379)      // monitor
    readonly property string controlCenter: icons.glyph(0xF062E) // tune
    readonly property string diagnostics: icons.glyph(0xF04D9)   // stethoscope
    readonly property string isolation: icons.glyph(0xF0328)     // layers
    readonly property string launcher: icons.glyph(0xF0349)      // magnify
    readonly property string theme: icons.glyph(0xF03D8)         // palette
    readonly property string wallpaper: icons.glyph(0xF0E09)     // wallpaper
    readonly property string keyboard: icons.glyph(0xF030C)      // keyboard
    readonly property string host: icons.glyph(0xF048B)          // server
    readonly property string details: icons.glyph(0xF02FD)       // information outline
    readonly property string session: icons.glyph(0xF0004)       // account
    readonly property string connect: icons.glyph(0xF0339)       // link
    // `console` is a reserved name in QML; the transport glyph is named for
    // what it is rather than for the word an operator reads beside it.
    readonly property string consoleTransport: icons.glyph(0xF018D)
    readonly property string search: icons.glyph(0xF0349)        // magnify
    readonly property string back: icons.glyph(0xF004D)          // arrow left
    readonly property string grid: icons.glyph(0xF0A2F)          // view grid outline
    readonly property string list: icons.glyph(0xF0279)          // format list

    // Hardware and telemetry.
    readonly property string gpu: icons.glyph(0xF08AE)           // expansion card
    readonly property string memory: icons.glyph(0xF035B)        // memory
    readonly property string temperature: icons.glyph(0xF050F)   // thermometer
    readonly property string networkWifi: icons.glyph(0xF05A9)   // wifi
    readonly property string networkWired: icons.glyph(0xF0200)  // ethernet
    readonly property string networkOff: icons.glyph(0xF0317)    // lan
    readonly property string audio: icons.glyph(0xF057E)         // volume high
    readonly property string audioMuted: icons.glyph(0xF0581)    // volume off
    readonly property string battery: icons.glyph(0xF0079)       // battery
    readonly property string power: icons.glyph(0xF0425)         // power
    readonly property string systemMenu: icons.glyph(0xF0493)    // cog

    // Machine state, neutral.
    readonly property string stateRunning: icons.glyph(0xF040A)  // play
    readonly property string statePaused: icons.glyph(0xF03E4)   // pause
    readonly property string stateOff: icons.glyph(0xF0425)      // power
    readonly property string stateUnknown: icons.glyph(0xF02D6)  // help

    // Chrome.
    readonly property string chevron: icons.glyph(0xF0142)       // chevron right
    readonly property string check: icons.glyph(0xF012C)         // check
    readonly property string close: icons.glyph(0xF0156)         // close
    readonly property string warning: icons.glyph(0xF0026)       // alert outline
    readonly property string unknown: icons.glyph(0xF02D6)       // help
    readonly property string urgent: "!"

    // The link kind comes from the bridge as a structured field. Display text
    // never decides which glyph appears.
    function networkGlyph(payload) {
        switch (String(payload.kind)) {
        case "wifi":
            return icons.networkWifi;
        case "wired":
            return icons.networkWired;
        case "offline":
            return icons.networkOff;
        default:
            return icons.unknown;
        }
    }

    // Audio state comes from the structured level, never from display text.
    function audioGlyph(level) {
        if (level && level.known === true)
            return level.muted === true ? icons.audioMuted : icons.audio;

        return icons.audio;
    }

    function machineStateGlyph(state) {
        switch (String(state).toLowerCase()) {
        case "running":
            return icons.stateRunning;
        case "paused":
        case "pmsuspended":
            return icons.statePaused;
        case "shut off":
        case "shutoff":
            return icons.stateOff;
        default:
            return icons.stateUnknown;
        }
    }

    // Sentence-case state words for reading; the host's raw state stays
    // available where the exact value matters.
    function machineStateWord(state) {
        const raw = String(state).toLowerCase();

        switch (raw) {
        case "running":
            return "Running";
        case "paused":
            return "Paused";
        case "pmsuspended":
            return "Suspended";
        case "shut off":
        case "shutoff":
            return "Shut off";
        case "crashed":
            return "Crashed";
        // Product Machine states that have no libvirt counterpart.
        case "not-created":
            return "Not created";
        case "configuration-drift":
            return "Configuration drift";
        case "runtime-unavailable":
            return "Runtime unavailable";
        case "unknown":
            return "State unknown";
        default:
            return raw.length > 0 ? raw.charAt(0).toUpperCase() + raw.slice(1) : "State unknown";
        }
    }
}
