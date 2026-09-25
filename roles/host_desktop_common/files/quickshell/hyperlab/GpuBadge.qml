// HyperLab GPU summary (V447-C9.3).
//
// One compact entry, one fact at a time, each with the scope it belongs to:
//
//   GPU: <machine>   a running machine currently holds the device
//   Boot: DEV 2      the host retains a boot claim and nothing holds it
//   GPU unreadable   the ownership source did not answer
//   GPU stale        the last ownership reading is too old to be current
//   Boot unknown     the boot claim could not be read; a previously seen
//                    claim is kept and marked "last seen"
//
// The routine idle case — ownership known, nobody holds it, a current
// reading of no claim — is deliberately silent on the rail and lives in
// Diagnostics. Unknown ownership and "nobody owns it" are different
// sentences and never share one, and neither are "the claim could not be
// read" and "there is no claim". Activation opens Diagnostics at Isolation
// and GPU.

import QtQuick

ShellControl {
    id: badge

    required property var payload
    required property var claim
    required property var ownership
    required property var icons
    required property string sourceState

    // ShellState.trustClaimState for the boot claim: loading, ok, stale or
    // unavailable. The claim itself is only current when this is "ok".
    required property string claimState

    signal detailsRequested()

    readonly property bool unreadable:
        badge.sourceState === "unavailable"
        || String(badge.payload.class) === "error"
        || String(badge.payload.class) === "bad"

    // An ownership reading that has aged out is not a current owner.
    readonly property bool ownershipStale:
        !badge.unreadable && badge.sourceState === "stale"

    readonly property bool unknown:
        !badge.unreadable
        && !badge.ownershipStale
        && badge.ownership.known !== true

    readonly property bool held:
        !badge.unreadable
        && !badge.ownershipStale
        && badge.ownership.known === true
        && String(badge.ownership.owner).length > 0

    readonly property bool claimCurrent: badge.claimState === "ok"

    // Loading is a short start-up wait; ShellState turns a source that never
    // answers into "unavailable", which is material.
    readonly property bool claimProblem:
        badge.claimState === "stale" || badge.claimState === "unavailable"

    readonly property bool claimed: badge.claim.claimed === true

    readonly property string identityWord:
        badge.claimed
        ? badge.theme.provenanceLabel(badge.claim.identity)
        : ""

    readonly property string claimText: {
        if (badge.claimProblem)
            return badge.claimed
                ? badge.identityWord + " " + badge.claim.level + " last seen"
                : "Claim unknown";

        return badge.identityWord + " " + badge.claim.level;
    }

    // Nothing to report is nothing shown: a free GPU at idle is not news.
    readonly property bool material:
        badge.unreadable
        || badge.ownershipStale
        || badge.unknown
        || badge.held
        || badge.claimProblem
        || (badge.claimCurrent && badge.claimed)

    // The GPU reading takes the main slot when it is itself material; the
    // boot claim then rides along as a qualifier when it is in doubt.
    readonly property bool ownershipLeads:
        badge.unreadable || badge.ownershipStale || badge.unknown || badge.held

    readonly property string scopeText: badge.ownershipLeads ? "GPU" : "Boot"

    readonly property string stateText: {
        if (badge.unreadable)
            return "Unreadable";

        if (badge.ownershipStale)
            return "Stale reading";

        if (badge.unknown)
            return "Ownership unknown";

        if (badge.held)
            return String(badge.ownership.owner);

        return badge.claimText;
    }

    readonly property color stateTone: {
        if (badge.unreadable)
            return badge.theme.semanticStatusColor("bad");

        if (badge.ownershipStale || badge.unknown)
            return badge.theme.semanticStatusColor("warn");

        if (badge.held)
            return badge.theme.textPrimary;

        if (badge.claimProblem)
            return badge.theme.semanticStatusColor("warn");

        return badge.theme.provenanceColor(badge.claim.identity);
    }

    objectName: "gpu-badge"
    visible: badge.material
    flat: true

    accessibleName:
        badge.scopeText + " " + badge.stateText
        + (badge.ownershipLeads && badge.claimProblem
            ? ", boot " + badge.claimText
            : "")
    Accessible.description: "Open isolation and GPU diagnostics"

    content: [
        ShellIcon {
            anchors.verticalCenter: parent.verticalCenter
            tokens: badge.tokens
            text: badge.icons.gpu
            color: badge.theme.textSecondary
        },

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: badge.tokens
            role: "bar"
            font.weight: Font.Normal
            text: badge.scopeText + " ·"
            color: badge.theme.textSecondary
        },

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: badge.tokens
            role: "bar"
            text: badge.stateText
            color: badge.stateTone

            Behavior on color {
                ColorAnimation {
                    duration: badge.tokens.motionHover
                }
            }
        },

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            visible: badge.ownershipLeads && badge.claimProblem
            tokens: badge.tokens
            role: "bar"
            font.weight: Font.Normal
            text: "· Boot " + badge.claimText
            color: badge.theme.semanticStatusColor("warn")
        }
    ]

    onActivated: badge.detailsRequested()
}
