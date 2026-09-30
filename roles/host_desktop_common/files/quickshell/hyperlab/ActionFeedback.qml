// HyperLab action feedback (V447-C9.3).
//
// One presentation for the life of a host or machine operation. It owns no
// truth: it renders the record the action layer published and nothing else,
// so managed execution remains separate from inventory-verified completion.
//
//   accepted   the bridge took the request
//   pending    the operation is running
//   completed  the bridge reported success
//   failed     the bridge reported failure
//   refused    the bridge declined before doing anything
//
// A refusal reason is host text and is shown verbatim.

import QtQuick

Item {
    id: feedback

    required property var tokens
    required property var theme
    required property var record

    readonly property string phase:
        feedback.record ? String(feedback.record.phase) : ""

    readonly property bool active: feedback.phase.length > 0

    readonly property string statusClass: {
        switch (feedback.phase) {
        case "interrupted":
        case "unverified":
        case "failed":
        case "refused":
            return "bad";
        case "completed":
            return "ok";
        default:
            return "";
        }
    }

    readonly property string headline: {
        if (!feedback.record)
            return "";

        const target = String(feedback.record.target);
        const verb = String(feedback.record.label);

        switch (feedback.phase) {
        case "requested":
        case "dispatched":
            return verb + " requested for " + target;
        case "running":
            return verb + " running for " + target;
        case "verifying":
            return verb + " finished — verifying " + target;
        case "interrupted":
            return verb + " interrupted for " + target;
        case "unverified":
            return verb + " state not verified for " + target;
        case "accepted":
            return verb + " accepted for " + target;
        case "pending":
            return verb + " running on " + target;
        case "completed":
            return verb + " completed on " + target;
        case "failed":
            return verb + " failed on " + target;
        case "refused":
            return verb + " refused for " + target;
        default:
            return "";
        }
    }

    visible: feedback.active
    implicitHeight: feedback.active ? column.implicitHeight : 0

    Accessible.role: Accessible.StaticText
    Accessible.name: feedback.headline

    Column {
        id: column

        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 2

        Row {
            spacing: feedback.tokens.spaceSm

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: feedback.tokens.spaceSm
                height: feedback.tokens.spaceSm
                radius: width / 2
                color:
                    feedback.statusClass.length > 0
                    ? feedback.theme.semanticStatusColor(feedback.statusClass)
                    : feedback.theme.textSecondary
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                tokens: feedback.tokens
                role: "meta"
                text: feedback.headline
                color: feedback.theme.textPrimary
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                visible: text.length > 0
                tokens: feedback.tokens
                role: "mono"
                text: feedback.record ? String(feedback.record.at) : ""
                color: feedback.theme.textQuiet
            }
        }

        ShellLabel {
            width: parent.width
            visible: text.length > 0
            tokens: feedback.tokens
            role: "meta"
            wrapMode: Text.WordWrap
            text: feedback.record ? String(feedback.record.detail) : ""
            color: feedback.theme.textQuiet
        }
    }
}
