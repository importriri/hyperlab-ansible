// HyperLab host telemetry summary (V447-C9.3).
//
// The compact host reading used inside Diagnostics: what the memory number
// means, who owns the GPU, which sensor the temperature comes from, which
// interface carries the network, and when the shell last observed them.
//
// This is deliberately not desktop furniture. The idle desktop shows no
// telemetry at all, so this component exists once, inside the workspace that
// exists to explain observations. Truthful values only, on the reviewed slow
// cadence; no graphs, no invented history.

import QtQuick

Item {
    id: footer

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState

    readonly property var ownership: footer.shellState.gpuOwnership

    readonly property string gpuOwnerText:
        footer.ownership.known
        ? (String(footer.ownership.owner).length > 0
            ? String(footer.ownership.owner)
            : "No current owner")
        : "Unknown"

    readonly property string networkKind: {
        switch (String(footer.shellState.networkPayload.kind)) {
        case "wifi":
            return "Wi-Fi";
        case "wired":
            return "Wired";
        case "offline":
            return "Offline";
        default:
            return "Unknown";
        }
    }

    function scopeOf(payload, fallback) {
        const detail = String(payload.detail);

        return detail.length > 0 ? detail : fallback;
    }

    implicitHeight:
        meters.implicitHeight
        + footer.tokens.spaceMd
        + observed.implicitHeight

    Flow {
        id: meters

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: footer.tokens.spaceHuge

        ResourceMeter {
            tokens: footer.tokens
            theme: footer.theme
            label: "Memory"
            scope: "Assignable to machines"
            payload: footer.shellState.ramPayload
        }

        ResourceMeter {
            tokens: footer.tokens
            theme: footer.theme
            label: "GPU"
            scope: footer.ownership.known
                ? (footer.ownership.bound
                    ? "Current owner · VFIO bound"
                    : "Current owner · not bound")
                : "Ownership not reported"
            payload: footer.shellState.gpuPayload
            valueOverride: footer.gpuOwnerText
            neutral: true
        }

        ResourceMeter {
            tokens: footer.tokens
            theme: footer.theme
            label: "Temperature"
            scope: footer.scopeOf(
                footer.shellState.temperaturePayload,
                "Sensor not reported"
            )
            payload: footer.shellState.temperaturePayload
        }

        ResourceMeter {
            tokens: footer.tokens
            theme: footer.theme
            label: "Network"
            scope: footer.scopeOf(
                footer.shellState.networkPayload,
                "Default route"
            )
            payload: footer.shellState.networkPayload
            valueOverride: footer.networkKind
        }
    }

    ShellLabel {
        id: observed

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: meters.bottom
        anchors.topMargin: footer.tokens.spaceMd

        tokens: footer.tokens
        role: "meta"
        text:
            footer.shellState.telemetryObservedAt > 0
            ? "Observed "
                + footer.shellState.observedText(
                    footer.shellState.telemetryObservedAt
                  )
                + " · "
                + footer.shellState.observedAge(
                    footer.shellState.telemetryObservedAt
                  )
                + " · every "
                + footer.shellState.slowPollSeconds + " s"
            : "Awaiting first observation"
        color: footer.theme.textQuiet
    }
}
