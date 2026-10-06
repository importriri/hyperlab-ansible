// HyperLab USB devices (ADR 0038, roadmap milestone 10).
//
// USBGuard blocks every USB device the host policy does not name. This view
// shows the devices the kernel reports, blocked ones first, and lets the
// operator allow a blocked one for this insertion or always. A device is
// never a Machine and is never passed to one from here.
//
// The list is the bridge's answer and is presentation only. Allowing hands
// the device's port to the bridge, which reads the list again and refuses a
// device that is not blocked or presents a keyboard or mouse; the reviewed
// playbook then checks the device once more as root, in the operation
// window that asks for the password. A device that presents a keyboard or
// mouse is allowed only from a terminal, after the operator has checked it.

import QtQuick

Item {
    id: view

    required property var tokens
    required property var theme
    required property var icons
    required property var machineActions
    required property var shellSurfaces

    readonly property var devices: view.machineActions.usbDevices
    readonly property string readState: view.machineActions.usbState

    function refresh() {
        view.machineActions.requestUsb();
    }

    function nameFor(device) {
        return device.product || device.manufacturer || "USB device";
    }

    // What a device presents, from its interface classes.
    function classWord(code) {
        switch (String(code)) {
        case "01":
            return "audio";
        case "02":
            return "communications";
        case "03":
            return "keyboard or mouse";
        case "06":
            return "camera or scanner";
        case "07":
            return "printer";
        case "08":
            return "storage";
        case "09":
            return "hub";
        case "0a":
            return "data";
        case "0b":
            return "smart card";
        case "0e":
            return "video";
        case "e0":
            return "wireless";
        case "ef":
            return "miscellaneous";
        case "ff":
            return "vendor specific";
        default:
            return "class " + String(code);
        }
    }

    function interfacesText(device) {
        if (!device.interfaces.length)
            return "What it presents could not be read";
        return device.interfaces.map(code => view.classWord(code))
            .filter((word, index, all) => all.indexOf(word) === index)
            .join(", ");
    }

    function stateWord(device) {
        return device.authorized === 0 ? "Blocked"
            : device.authorized === 1 ? "Allowed"
            : "Authorization unknown";
    }

    // Why this device cannot be allowed here; "" when it can. The bridge and
    // the playbook decide for real.
    function refusal(device) {
        if (device.authorized === 1)
            return "Already allowed";
        if (device.authorized !== 0)
            return "Its authorization could not be read";
        if (device.hid)
            return "A device that presents a keyboard or mouse is allowed only from a terminal";
        if (!device.interfaces.length)
            return "What it presents could not be read; allow it from a terminal";
        return "";
    }

    function actionsFor(device) {
        const reason = view.refusal(device);
        return [
            { "scope": "once", "label": "Allow once", "enabled": reason === "",
              "reason": reason },
            { "scope": "permanent", "label": "Allow always", "enabled": reason === "",
              "reason": reason }
        ];
    }

    onVisibleChanged: {
        if (view.visible)
            view.refresh();
    }

    Timer {
        interval: 15000
        running: view.visible
        repeat: true
        onTriggered: view.refresh()
    }

    Connections {
        target: view.machineActions

        function onInventoryRefreshRequested() {
            if (view.visible)
                view.refresh();
        }
    }

    WorkspaceFrame {
        id: frame

        anchors.fill: parent
        tokens: view.tokens
        theme: view.theme

        title: "USB devices"
        subtitle: "A new USB device stays blocked until you allow it."
        maxContentWidth: 1040

        Column {
            width: frame.bodyWidth
            spacing: view.tokens.spaceLg

            SectionHeader {
                width: parent.width
                tokens: view.tokens
                theme: view.theme
                label: "Devices"
                description:
                    "Allow once lets a blocked device in until it is unplugged. Allow "
                    + "always also appends a rule for it to the USBGuard policy. The "
                    + "operation window asks for your password."
            }

            EmptyState {
                width: parent.width
                visible: view.readState !== "ready"
                tokens: view.tokens
                theme: view.theme
                kind: view.readState === "unavailable" ? "unavailable" : "empty"
                title: {
                    switch (view.readState) {
                    case "unavailable":
                        return "The USB devices could not be read";
                    case "empty":
                        return "No USB devices are attached";
                    default:
                        return "Reading the USB devices";
                    }
                }
                description: {
                    switch (view.readState) {
                    case "unavailable":
                        return view.machineActions.usbDetail;
                    case "empty":
                        return "Only the root hubs are present.";
                    default:
                        return "";
                    }
                }
            }

            Repeater {
                model: view.readState === "ready" ? view.devices : []

                ShellCard {
                    id: card

                    required property var modelData

                    objectName: "usb-" + card.modelData.port
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    accessibleName: "USB device " + view.nameFor(card.modelData)
                        + " at port " + card.modelData.port

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: view.tokens.spaceSm

                        Row {
                            spacing: view.tokens.spaceMd

                            ShellLabel {
                                tokens: view.tokens
                                role: "heading"
                                text: view.nameFor(card.modelData)
                                color: view.theme.textPrimary
                            }

                            ShellLabel {
                                tokens: view.tokens
                                role: "meta"
                                text: card.modelData.vendor_id + ":"
                                    + (card.modelData.product_id || "????")
                                    + " · port " + card.modelData.port
                                color: view.theme.textSecondary
                            }
                        }

                        ShellLabel {
                            width: parent.width
                            tokens: view.tokens
                            role: "meta"
                            wrapMode: Text.Wrap
                            text: view.stateWord(card.modelData) + " · "
                                + view.interfacesText(card.modelData)
                                + (card.modelData.manufacturer && card.modelData.product
                                    ? " · " + card.modelData.manufacturer : "")
                            color: card.modelData.authorized === 0
                                ? view.theme.semanticStatusColor("warn")
                                : view.theme.textSecondary
                        }

                        Row {
                            spacing: view.tokens.spaceSm

                            Repeater {
                                model: view.actionsFor(card.modelData)

                                ShellControl {
                                    id: control

                                    required property var modelData

                                    objectName: "usb-" + control.modelData.scope
                                        + "-" + card.modelData.port
                                    tokens: view.tokens
                                    theme: view.theme
                                    enabled: control.modelData.enabled
                                    busy: view.machineActions.usbBusy(card.modelData.port)
                                    disabledReason: control.modelData.reason
                                    accessibleName: control.modelData.label + " "
                                        + view.nameFor(card.modelData)

                                    content: [
                                        ShellLabel {
                                            anchors.verticalCenter: parent.verticalCenter
                                            tokens: view.tokens
                                            role: "body"
                                            text: control.modelData.label
                                            color: view.theme.textPrimary
                                        }
                                    ]

                                    onActivated: {
                                        view.machineActions.allowUsb(
                                            card.modelData.port,
                                            control.modelData.scope
                                        );
                                    }
                                }
                            }
                        }

                        // The reason is read, not only announced: an
                        // operator looking at a disabled action sees why.
                        ShellLabel {
                            objectName: "usb-reason-" + card.modelData.port
                            width: parent.width
                            visible: text.length > 0
                            tokens: view.tokens
                            role: "meta"
                            wrapMode: Text.Wrap
                            text: view.refusal(card.modelData)
                            color: card.modelData.hid
                                ? view.theme.semanticStatusColor("warn")
                                : view.theme.textSecondary
                        }
                    }
                }
            }
        }
    }
}
