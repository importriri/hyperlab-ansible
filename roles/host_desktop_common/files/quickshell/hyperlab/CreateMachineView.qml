// HyperLab Create view (ADR 0017).
//
// A Machine from a reviewed Template: name, network and resources, inside
// the limits the Machine factory reported. The view never decides what is
// allowed: it shows the plan the bridge returned, builds a request from it
// through ShellState, and hands positional values to the bridge, which
// checks them again before the factory does.
//
// Nothing secret is typed here. The guest key is the host's own, shown only
// by fingerprint; a workstation password and the host's become prompt are
// asked in the operation window that provisioning opens.

import QtQuick

Item {
    id: view

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var machineActions
    required property var shellSurfaces

    signal closed()

    property string templateId: ""
    property string lifecycle: ""
    property string network: ""
    property string profile: ""

    readonly property var plan: view.shellState.createPlan
    readonly property var template: view.shellState.createTemplate(view.templateId)

    readonly property var form: ({
        "template": view.templateId,
        "name": nameInput.text,
        "lifecycle": view.lifecycle,
        "network": view.network,
        "profile": view.profile,
        "memory": memoryInput.text,
        "vcpus": vcpuInput.text,
        "disk": diskInput.text
    })

    readonly property string problem: view.shellState.createProblem(view.form)

    readonly property string phase:
        view.machineActions.createMachine === nameInput.text
        ? view.machineActions.createPhase
        : ""

    function choose(identifier) {
        const entry = view.shellState.createTemplate(identifier);

        if (entry === null || !entry.creatable)
            return;

        view.templateId = entry.id;
        view.lifecycle = entry.defaultLifecycle;
        view.network = entry.defaultNetwork;
        view.profile = entry.defaultProfile;

        if (entry.custom !== null) {
            memoryInput.text = String(entry.custom.memoryMin);
            vcpuInput.text = String(Math.min(2, entry.custom.vcpusMax));
            diskInput.text = String(entry.custom.diskMin);
        }
    }

    function profileSummary(entry, name) {
        if (name === "custom")
            return "Choose memory, vCPUs and disk";

        const values = entry.profiles[name];

        if (!values)
            return "";

        return values.vcpus + " vCPU · "
            + (values.memory_mb === "auto"
                ? "memory from the host budget"
                : values.memory_mb + " MB")
            + " · " + values.disk_gib + " GiB";
    }

    function submit() {
        const args = view.shellState.createArguments(view.form);

        if (args === null || view.machineActions.creating)
            return;

        view.machineActions.submitCreate(args);
    }

    // A dispatched request opens the new Machine: its pane shows the
    // provisioning operation and reopens its window.
    Connections {
        target: view.machineActions

        function onCreatePhaseChanged() {
            if (
                view.machineActions.createPhase === "dispatched"
                && view.machineActions.createMachine === nameInput.text
            ) {
                view.shellSurfaces.selectMachine(
                    nameInput.text,
                    view.shellState.machinesGeneration,
                    false
                );
                view.closed();
            }
        }
    }

    Component.onCompleted: view.machineActions.requestCreatePlan()

    WorkspaceFrame {
        id: frame

        anchors.fill: parent
        tokens: view.tokens
        theme: view.theme
        maxContentWidth: 760

        title: "New Machine"
        subtitle:
            view.plan.state === "ok"
            ? "From a reviewed Template · the host checks every value again"
            : (view.plan.state === "unavailable"
                ? "Creation plan unavailable"
                : "Reading the Templates")
        subtitleClass: view.plan.state === "unavailable" ? "warn" : ""

        trailing: [
            ShellControl {
                objectName: "createBack"
                anchors.verticalCenter: parent.verticalCenter
                height: view.tokens.controlHeightLarge
                tokens: view.tokens
                theme: view.theme
                flat: true
                accessibleName: "Back to Machines"

                content: [
                    ShellLabel {
                        anchors.verticalCenter: parent.verticalCenter
                        tokens: view.tokens
                        role: "label"
                        text: "Back to Machines"
                        color: view.theme.textSecondary
                    }
                ]

                onActivated: view.closed()
            }
        ]

        Column {
            width: frame.bodyWidth
            spacing: view.tokens.spaceXl

            EmptyState {
                width: parent.width
                visible: view.plan.state === "unavailable"
                tokens: view.tokens
                theme: view.theme
                kind: "unavailable"
                title: "The creation plan cannot be read"
                description: view.plan.detail
            }

            // ---------------------------------------------------- Template
            Column {
                width: parent.width
                spacing: view.tokens.spaceMd
                visible: view.plan.state === "ok"

                SectionHeader {
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    label: "Template"
                    description: "Each Template pins one sealed image and what a Machine may be."
                }

                Flow {
                    width: parent.width
                    spacing: view.tokens.cardGap

                    Repeater {
                        model: view.plan.templates

                        delegate: ShellControl {
                            required property var modelData

                            objectName: "createTemplate-" + modelData.id
                            width: Math.min(360, frame.bodyWidth)
                            height: templateText.implicitHeight + view.tokens.spaceLg * 2
                            tokens: view.tokens
                            theme: view.theme
                            enabled: modelData.creatable
                            selected: view.templateId === modelData.id
                            accessibleName: modelData.displayName
                            disabledReason: modelData.blockedReason

                            content: [
                                Column {
                                    id: templateText
                                    width: frame.bodyWidth > 360 ? 360 - view.tokens.controlPadding * 2
                                        : frame.bodyWidth - view.tokens.controlPadding * 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: view.tokens.spaceXs

                                    ShellLabel {
                                        width: parent.width
                                        tokens: view.tokens
                                        role: "heading"
                                        text: modelData.displayName
                                        color: view.theme.textPrimary
                                    }

                                    ShellLabel {
                                        width: parent.width
                                        tokens: view.tokens
                                        role: "meta"
                                        text:
                                            (modelData.password
                                                ? "Workstation · desktop and password"
                                                : "Server · SSH only")
                                            + (modelData.device === "vfio" ? " · dedicated GPU" : "")
                                            + (modelData.os.length > 0 ? " · " + modelData.os : "")
                                        color: view.theme.textSecondary
                                        wrapMode: Text.Wrap
                                    }

                                    ShellLabel {
                                        width: parent.width
                                        visible: !modelData.creatable
                                        tokens: view.tokens
                                        role: "meta"
                                        text: modelData.blockedReason
                                        color: view.theme.semanticStatusColor("warn")
                                        wrapMode: Text.Wrap
                                    }
                                }
                            ]

                            onActivated: view.choose(modelData.id)
                        }
                    }
                }
            }

            // ------------------------------------------------- the Machine
            Column {
                width: parent.width
                spacing: view.tokens.spaceLg
                visible: view.plan.state === "ok" && view.template !== null

                SectionHeader {
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    label: "Name"
                    description: "2 to 31 lowercase letters, digits or dashes. It names the domain and the guest."
                }

                Rectangle {
                    width: Math.min(360, parent.width)
                    height: view.tokens.controlHeightLarge
                    radius: view.tokens.radiusControl
                    color: view.theme.raised
                    border.width: nameInput.activeFocus ? view.tokens.focusOutline : view.tokens.borderSize
                    border.color: nameInput.activeFocus ? view.theme.focusRing : view.theme.boundary

                    TextInput {
                        id: nameInput

                        objectName: "createName"
                        anchors.fill: parent
                        anchors.leftMargin: view.tokens.spaceMd
                        anchors.rightMargin: view.tokens.spaceMd
                        verticalAlignment: TextInput.AlignVCenter
                        font.family: view.tokens.fontMono
                        font.pixelSize: view.tokens.fontBody
                        color: view.theme.textPrimary
                        selectionColor: view.theme.fillSelected
                        selectedTextColor: view.theme.textPrimary
                        maximumLength: 31
                        activeFocusOnTab: true
                        clip: true
                        validator: RegularExpressionValidator { regularExpression: /[a-z0-9-]*/ }

                        Accessible.role: Accessible.EditableText
                        Accessible.name: "Machine name"
                    }
                }

                SectionHeader {
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    label: "Lifecycle"
                    description: "Permanent keeps its disk. Disposable throws away everything it wrote whenever it stops."
                }

                Flow {
                    width: parent.width
                    spacing: view.tokens.spaceSm

                    Repeater {
                        model: view.template !== null ? view.template.lifecycles : []

                        delegate: ShellControl {
                            required property var modelData

                            objectName: "createLifecycle-" + modelData
                            width: Math.min(300, frame.bodyWidth)
                            height: lifecycleText.implicitHeight + view.tokens.spaceMd * 2
                            tokens: view.tokens
                            theme: view.theme
                            selected: view.lifecycle === modelData
                            accessibleName: modelData + " Machine"

                            content: [
                                Column {
                                    id: lifecycleText
                                    width: Math.min(300, frame.bodyWidth) - view.tokens.controlPadding * 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: view.tokens.spaceXs

                                    ShellLabel {
                                        tokens: view.tokens
                                        role: "label"
                                        text: modelData === "disposable" ? "Disposable" : "Permanent"
                                        color: view.theme.textPrimary
                                    }

                                    ShellLabel {
                                        width: parent.width
                                        tokens: view.tokens
                                        role: "meta"
                                        wrapMode: Text.Wrap
                                        color: view.theme.textSecondary
                                        text:
                                            modelData === "disposable"
                                            ? "Every start is a fresh first boot from the sealed image"
                                            : "An independent copy; what it writes stays"
                                    }
                                }
                            ]

                            onActivated: view.lifecycle = modelData
                        }
                    }
                }

                SectionHeader {
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    label: "Network"
                    description: "The network is the Machine's identity: the host frame shows it in this colour."
                }

                Flow {
                    width: parent.width
                    spacing: view.tokens.spaceSm

                    Repeater {
                        model: view.template !== null ? view.template.networks : []

                        delegate: ShellControl {
                            required property var modelData

                            objectName: "createNetwork-" + modelData
                            height: view.tokens.controlHeightLarge
                            tokens: view.tokens
                            theme: view.theme
                            selected: view.network === modelData
                            accessibleName: view.theme.provenanceLabel(modelData) + " network"

                            content: [
                                ProvenanceMarker {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: view.tokens
                                    theme: view.theme
                                    identity: modelData
                                },
                                ShellLabel {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: view.tokens
                                    role: "label"
                                    text: view.theme.provenanceLabel(modelData)
                                    color: view.theme.textPrimary
                                }
                            ]

                            onActivated: view.network = modelData
                        }
                    }
                }

                SectionHeader {
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    label: "Resources"
                    description: "Memory is allocated, not consumed; the host refuses a Machine its budget cannot hold."
                }

                Flow {
                    width: parent.width
                    spacing: view.tokens.spaceSm

                    Repeater {
                        model: view.template !== null ? view.template.resourceProfiles : []

                        delegate: ShellControl {
                            required property var modelData

                            objectName: "createProfile-" + modelData
                            width: Math.min(240, frame.bodyWidth)
                            height: profileText.implicitHeight + view.tokens.spaceMd * 2
                            tokens: view.tokens
                            theme: view.theme
                            selected: view.profile === modelData
                            accessibleName: modelData + " resources"

                            content: [
                                Column {
                                    id: profileText
                                    width: Math.min(240, frame.bodyWidth) - view.tokens.controlPadding * 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: view.tokens.spaceXs

                                    ShellLabel {
                                        tokens: view.tokens
                                        role: "label"
                                        text: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                                        color: view.theme.textPrimary
                                    }

                                    ShellLabel {
                                        width: parent.width
                                        tokens: view.tokens
                                        role: "meta"
                                        text: view.template !== null
                                            ? view.profileSummary(view.template, modelData) : ""
                                        color: view.theme.textSecondary
                                        wrapMode: Text.Wrap
                                    }
                                }
                            ]

                            onActivated: view.profile = modelData
                        }
                    }
                }

                // Custom values, each beside the limit it is checked against.
                Flow {
                    width: parent.width
                    spacing: view.tokens.spaceLg
                    visible: view.profile === "custom" && view.template !== null
                        && view.template.custom !== null

                    Column {
                        spacing: view.tokens.spaceXs

                        ShellLabel {
                            tokens: view.tokens
                            role: "label"
                            text: "Memory (MB)"
                            color: view.theme.textSecondary
                        }

                        ShellLabel {
                            tokens: view.tokens
                            role: "meta"
                            color: view.theme.textQuiet
                            text: view.template !== null && view.template.custom !== null
                                ? "at least " + view.template.custom.memoryMin : ""
                        }

                        Rectangle {
                            width: 150
                            height: view.tokens.controlHeightLarge
                            radius: view.tokens.radiusControl
                            color: view.theme.raised
                            border.width: memoryInput.activeFocus ? view.tokens.focusOutline : view.tokens.borderSize
                            border.color: memoryInput.activeFocus ? view.theme.focusRing : view.theme.boundary

                            TextInput {
                                id: memoryInput
                                objectName: "createMemory"
                                anchors.fill: parent
                                anchors.leftMargin: view.tokens.spaceMd
                                anchors.rightMargin: view.tokens.spaceMd
                                verticalAlignment: TextInput.AlignVCenter
                                font.family: view.tokens.fontMono
                                font.pixelSize: view.tokens.fontBody
                                color: view.theme.textPrimary
                                selectionColor: view.theme.fillSelected
                                selectedTextColor: view.theme.textPrimary
                                activeFocusOnTab: true
                                maximumLength: 7
                                clip: true
                                validator: RegularExpressionValidator { regularExpression: /[0-9]*/ }
                                Accessible.role: Accessible.EditableText
                                Accessible.name: "Memory in megabytes"
                            }
                        }
                    }

                    Column {
                        spacing: view.tokens.spaceXs

                        ShellLabel {
                            tokens: view.tokens
                            role: "label"
                            text: "vCPUs"
                            color: view.theme.textSecondary
                        }

                        ShellLabel {
                            tokens: view.tokens
                            role: "meta"
                            color: view.theme.textQuiet
                            text: view.template !== null && view.template.custom !== null
                                ? view.template.custom.vcpusMin + " to " + view.template.custom.vcpusMax : ""
                        }

                        Rectangle {
                            width: 110
                            height: view.tokens.controlHeightLarge
                            radius: view.tokens.radiusControl
                            color: view.theme.raised
                            border.width: vcpuInput.activeFocus ? view.tokens.focusOutline : view.tokens.borderSize
                            border.color: vcpuInput.activeFocus ? view.theme.focusRing : view.theme.boundary

                            TextInput {
                                id: vcpuInput
                                objectName: "createVcpus"
                                anchors.fill: parent
                                anchors.leftMargin: view.tokens.spaceMd
                                anchors.rightMargin: view.tokens.spaceMd
                                verticalAlignment: TextInput.AlignVCenter
                                font.family: view.tokens.fontMono
                                font.pixelSize: view.tokens.fontBody
                                color: view.theme.textPrimary
                                selectionColor: view.theme.fillSelected
                                selectedTextColor: view.theme.textPrimary
                                activeFocusOnTab: true
                                maximumLength: 3
                                clip: true
                                validator: RegularExpressionValidator { regularExpression: /[0-9]*/ }
                                Accessible.role: Accessible.EditableText
                                Accessible.name: "Virtual CPUs"
                            }
                        }
                    }

                    Column {
                        spacing: view.tokens.spaceXs

                        ShellLabel {
                            tokens: view.tokens
                            role: "label"
                            text: "Disk (GiB)"
                            color: view.theme.textSecondary
                        }

                        ShellLabel {
                            tokens: view.tokens
                            role: "meta"
                            color: view.theme.textQuiet
                            text: view.template !== null && view.template.custom !== null
                                ? "at least " + view.template.custom.diskMin + ", the sealed image" : ""
                        }

                        Rectangle {
                            width: 150
                            height: view.tokens.controlHeightLarge
                            radius: view.tokens.radiusControl
                            color: view.theme.raised
                            border.width: diskInput.activeFocus ? view.tokens.focusOutline : view.tokens.borderSize
                            border.color: diskInput.activeFocus ? view.theme.focusRing : view.theme.boundary

                            TextInput {
                                id: diskInput
                                objectName: "createDisk"
                                anchors.fill: parent
                                anchors.leftMargin: view.tokens.spaceMd
                                anchors.rightMargin: view.tokens.spaceMd
                                verticalAlignment: TextInput.AlignVCenter
                                font.family: view.tokens.fontMono
                                font.pixelSize: view.tokens.fontBody
                                color: view.theme.textPrimary
                                selectionColor: view.theme.fillSelected
                                selectedTextColor: view.theme.textPrimary
                                activeFocusOnTab: true
                                maximumLength: 5
                                clip: true
                                validator: RegularExpressionValidator { regularExpression: /[0-9]*/ }
                                Accessible.role: Accessible.EditableText
                                Accessible.name: "Disk in gibibytes"
                            }
                        }
                    }
                }

                SectionHeader {
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    label: "Access"
                    description: "Secrets never pass through this view."
                }

                Column {
                    width: parent.width
                    spacing: view.tokens.spaceSm

                    ShellLabel {
                        objectName: "createKey"
                        width: parent.width
                        tokens: view.tokens
                        role: "mono"
                        wrapMode: Text.WrapAnywhere
                        text:
                            view.plan.guestKey !== null && view.plan.guestKey.available
                            ? "Guest key " + view.plan.guestKey.fingerprint
                            : "Guest key unavailable: "
                                + (view.plan.guestKey !== null ? view.plan.guestKey.reason : "")
                        color:
                            view.plan.guestKey !== null && view.plan.guestKey.available
                            ? view.theme.textSecondary
                            : view.theme.semanticStatusColor("warn")
                    }

                    ShellLabel {
                        width: parent.width
                        tokens: view.tokens
                        role: "body"
                        wrapMode: Text.Wrap
                        color: view.theme.textSecondary
                        text:
                            view.template !== null && view.template.password
                            ? "The operation window asks for the Machine account's password, "
                                + "hashes it and deletes the hash after the first profile pass. "
                                + "The host asks for your password there too."
                            : "The Machine is reached over SSH with this key only. "
                                + "The host asks for your password in the operation window."
                    }
                }
            }

            // ----------------------------------------------------- submit
            Column {
                width: parent.width
                spacing: view.tokens.spaceMd
                visible: view.plan.state === "ok"

                ShellDivider {
                    width: parent.width
                    vertical: false
                    tokens: view.tokens
                    theme: view.theme
                }

                ShellLabel {
                    objectName: "createProblem"
                    width: parent.width
                    tokens: view.tokens
                    role: "meta"
                    wrapMode: Text.Wrap
                    text:
                        view.phase === "refused" || view.phase === "failed"
                        ? view.machineActions.createDetail
                        : (view.phase === "pending"
                            ? "Recording " + nameInput.text + " and starting its provisioning"
                            : view.problem)
                    color:
                        view.phase === "refused" || view.phase === "failed"
                        ? view.theme.semanticStatusColor("critical")
                        : view.theme.textSecondary
                    visible: text.length > 0
                }

                ShellControl {
                    objectName: "createSubmit"
                    height: view.tokens.controlHeightLarge
                    tokens: view.tokens
                    theme: view.theme
                    enabled: view.problem.length === 0
                    busy: view.machineActions.creating
                    accessibleName: "Create Machine"
                    disabledReason: view.problem

                    content: [
                        ShellLabel {
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: view.tokens
                            role: "label"
                            text: "Create and provision"
                            color: view.theme.textPrimary
                        }
                    ]

                    onActivated: view.submit()
                }
            }
        }
    }
}
