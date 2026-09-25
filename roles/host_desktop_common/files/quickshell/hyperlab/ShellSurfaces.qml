// HyperLab native surface coordinator (V447-C9.3).
//
// This object owns where the product is, never what the host is. It holds
// the open product workspace, its destination and subpage, the identity of
// the selected machine, the transient surfaces and the one confirmation
// record. Observed host facts live in ShellState; transport lives in the
// action layer.
//
// Two rules make the rest of the shell safe:
//
//   * selection is a stable backend identifier, never a copied snapshot, so
//     a refreshed inventory can never leave a stale object behind;
//   * a confirmation captures its target once and is invalidated by any
//     navigation, selection or capability change, so it can never be
//     redirected at the moment it is executed.
//
// Presentation only: this object never touches a process, file or socket.

import QtQuick

QtObject {
    id: surfaces

    // Product destinations. These are native application destinations, not
    // compositor workspace numbers.
    readonly property var destinations: [
        "machines",
        "controls",
        "diagnostics"
    ]

    readonly property var subpages: ({
        "machines": ["inventory"],
        "controls": ["session", "audio", "appearance"],
        "diagnostics": ["overview", "isolation", "inventory", "session"]
    })

    property bool workspaceOpen: false
    property string workspaceView: "machines"
    property string subpage: "inventory"

    property bool launcherOpen: false
    property bool systemPanelOpen: false
    property bool topRailVisible: true

    // The output each transient surface was summoned from. One launcher,
    // one panel and one OSD answer at a time, each on the output that asked,
    // and showing one never moves another.
    property string launcherOrigin: ""
    property string panelOrigin: ""
    property string osdOrigin: ""

    // Supplied by the shell root from ShellState's observed focused output,
    // resolved against the live screens. A keyboard or IPC request carries no
    // output of its own, so it lands here; the pointer always names its own.
    property string activeOutput: ""

    // Names of the outputs that currently exist, also supplied by the root.
    // A transient whose output disappears is dismissed, never orphaned.
    property var liveOutputs: []

    // The stable backend identifier of the selected machine. Never an object.
    property string selectedMachineId: ""

    // Inventory generation observed when the selection was made, so a
    // confirmation can be invalidated when the inventory underneath changes.
    property int selectionGeneration: -1

    property string osdKind: ""
    property int osdSerial: 0

    // The host action this OSD reports on, if any. While `osdPending` the
    // card says so instead of showing the previous value; only the result of
    // this same action settles it, so an unrelated failure can never be
    // presented on it.
    property string osdAction: ""
    property bool osdPending: false
    property int osdSettledSerial: 0

    // A failed host action is reported on the card that was showing its
    // value, so a refusal is never presented as an unchanged success.
    property string osdFailure: ""

    property var confirmation: null

    signal workspaceOpened(string view)

    // The workspace was asked for while it was already open, possibly behind
    // other windows or on another compositor workspace. The window host
    // answers by asking the compositor, through the reviewed adapter, to
    // bring it forward.
    signal workspaceRaiseRequested()
    signal workspaceClosed()
    signal confirmationCancelled()

    function validWorkspace(candidate) {
        return surfaces.destinations.indexOf(String(candidate)) >= 0;
    }

    function validSubpage(view, candidate) {
        const pages = surfaces.subpages[String(view)];

        if (pages === undefined)
            return false;

        return pages.indexOf(String(candidate)) >= 0;
    }

    function defaultSubpage(view) {
        const pages = surfaces.subpages[String(view)];

        return pages === undefined ? "" : pages[0];
    }

    function toggleTopRail() {
        surfaces.topRailVisible = !surfaces.topRailVisible;
        return surfaces.topRailVisible;
    }

    function showTopRail() {
        surfaces.topRailVisible = true;
    }

    function hideTopRail() {
        surfaces.topRailVisible = false;
    }

    // Opening a destination is explicit. It dismisses transient surfaces,
    // cancels any armed confirmation and presents the workspace.
    function openWorkspace(view) {
        return surfaces.openWorkspacePage(view, "", true);
    }

    // Navigation inside the already-visible HyperLab workspace changes only
    // product state. It must not ask the compositor to refocus the window:
    // doing so can warp the pointer even though the operator never left it.
    function switchWorkspace(view) {
        return surfaces.openWorkspacePage(view, "", false);
    }

    function openWorkspacePage(view, page, raiseExisting) {
        const candidate = String(view);
        const shouldRaise =
            raiseExisting === undefined ? true : raiseExisting === true;

        if (!surfaces.validWorkspace(candidate))
            return false;

        surfaces.cancelConfirmation();
        surfaces.launcherOpen = false;
        surfaces.systemPanelOpen = false;

        const wanted = String(page);

        surfaces.workspaceView = candidate;
        surfaces.subpage =
            surfaces.validSubpage(candidate, wanted)
            ? wanted
            : surfaces.defaultSubpage(candidate);

        if (candidate !== "machines")
            surfaces.selectedMachineId = "";

        const alreadyOpen = surfaces.workspaceOpen;

        surfaces.workspaceOpen = true;
        surfaces.workspaceOpened(candidate);

        if (alreadyOpen && shouldRaise)
            surfaces.workspaceRaiseRequested();

        return true;
    }

    function openSubpage(page) {
        const wanted = String(page);

        if (!surfaces.validSubpage(surfaces.workspaceView, wanted))
            return false;

        surfaces.cancelConfirmation();
        surfaces.subpage = wanted;
        return true;
    }

    function closeWorkspace() {
        surfaces.cancelConfirmation();
        surfaces.workspaceOpen = false;
        surfaces.workspaceClosed();
    }

    function toggleWorkspace(view) {
        if (
            surfaces.workspaceOpen
            && surfaces.workspaceView === String(view)
        ) {
            surfaces.closeWorkspace();
            return false;
        }

        surfaces.openWorkspace(view);
        return true;
    }

    // Selection carries the backend identity and the generation it was
    // resolved against; the view resolves it against the current snapshot.
    function selectMachine(identifier, generation) {
        const name = String(identifier);

        if (name.length === 0)
            return false;

        surfaces.cancelConfirmation();
        surfaces.openWorkspace("machines");
        surfaces.selectedMachineId = name;
        surfaces.selectionGeneration =
            typeof generation === "number" ? generation : -1;
        return true;
    }

    function clearMachineSelection() {
        surfaces.cancelConfirmation();
        surfaces.selectedMachineId = "";
        surfaces.selectionGeneration = -1;
    }

    // An empty origin means "wherever the operator is": the observed active
    // output. It never means "every output".
    function resolveOrigin(origin) {
        const requested = String(origin);

        return requested.length > 0 ? requested : surfaces.activeOutput;
    }

    // A transient that summons over a dialog abandons the dialog: its target
    // and consequence are no longer what the operator is looking at.
    function openLauncher(origin) {
        surfaces.cancelConfirmation();
        surfaces.launcherOrigin = surfaces.resolveOrigin(origin);
        surfaces.systemPanelOpen = false;
        surfaces.launcherOpen = surfaces.launcherOrigin.length > 0;
    }

    function closeLauncher() {
        surfaces.launcherOpen = false;
    }

    function toggleLauncher(origin) {
        if (surfaces.launcherOpen)
            surfaces.closeLauncher();
        else
            surfaces.openLauncher(origin);
    }

    function openSystemPanel(origin) {
        surfaces.cancelConfirmation();
        surfaces.panelOrigin = surfaces.resolveOrigin(origin);
        surfaces.launcherOpen = false;
        surfaces.systemPanelOpen = surfaces.panelOrigin.length > 0;
    }

    function closeSystemPanel() {
        surfaces.systemPanelOpen = false;
    }

    function toggleSystemPanel(origin) {
        if (surfaces.systemPanelOpen)
            surfaces.closeSystemPanel();
        else
            surfaces.openSystemPanel(origin);
    }

    function dismissAll() {
        surfaces.cancelConfirmation();
        surfaces.launcherOpen = false;
        surfaces.systemPanelOpen = false;
    }

    // The session is being locked: nothing armed survives behind the locker.
    function sessionLocking() {
        surfaces.dismissAll();
    }

    function originFor(kind) {
        switch (String(kind)) {
        case "launcher":
            return surfaces.launcherOrigin;
        case "panel":
            return surfaces.panelOrigin;
        case "osd":
            return surfaces.osdOrigin;
        default:
            return "";
        }
    }

    // A transient surface belongs to the output that summoned it. An output
    // that never claimed one, or one that has been removed, shows nothing,
    // and no surface ever owns anything through an empty name.
    function ownsTransient(kind, name) {
        const output = String(name);
        const origin = surfaces.originFor(kind);

        return output.length > 0 && origin === output;
    }

    onLiveOutputsChanged: {
        const live = surfaces.liveOutputs || [];

        if (surfaces.launcherOpen && live.indexOf(surfaces.launcherOrigin) < 0)
            surfaces.launcherOpen = false;

        if (surfaces.systemPanelOpen && live.indexOf(surfaces.panelOrigin) < 0)
            surfaces.systemPanelOpen = false;

        if (live.indexOf(surfaces.osdOrigin) < 0) {
            surfaces.osdOrigin = "";
            surfaces.osdPending = false;
        }
    }

    function validOsdKind(kind) {
        const candidate = String(kind);

        return candidate === "audio"
            || candidate === "keyboard"
            || candidate === "theme"
            || candidate === "wallpaper";
    }

    // Show the host's current state for a kind, with no action attached:
    // the compositor already performed it (a volume key) or nothing did.
    function showOsd(kind, origin) {
        if (!surfaces.validOsdKind(kind))
            return false;

        const output = surfaces.resolveOrigin(origin);

        if (output.length === 0)
            return false;

        surfaces.osdOrigin = output;
        surfaces.osdKind = String(kind);
        surfaces.osdAction = "";
        surfaces.osdPending = false;
        surfaces.osdFailure = "";
        surfaces.osdSerial += 1;
        return true;
    }

    // Feedback for a host action the shell itself requested. `accepted` is
    // what the action layer returned: a refused or full queue is a failure
    // now, not a pending card that never settles.
    function showActionOsd(kind, action, accepted, origin) {
        if (!surfaces.showOsd(kind, origin))
            return false;

        surfaces.osdAction = String(action);

        if (accepted === true) {
            surfaces.osdPending = true;
        } else {
            surfaces.osdFailure = "The host did not accept this action";
            surfaces.osdSettledSerial += 1;
        }

        return true;
    }

    // Called with every host action result. Only the result of the action
    // the card is reporting on settles it.
    function settleActionOsd(action, ok, detail) {
        if (
            surfaces.osdAction.length === 0
            || surfaces.osdAction !== String(action)
            || !surfaces.osdPending
        )
            return;

        surfaces.osdPending = false;
        surfaces.osdFailure = ok === true ? "" : String(detail);
        surfaces.osdSettledSerial += 1;
    }

    // Confirmation. The record is captured whole and never re-read from the
    // live selection; `submitConfirmation` returns exactly one record, or
    // null when the dialog has already been spent or invalidated.
    function requestConfirmation(record) {
        if (
            record === null
            || record === undefined
            || typeof record !== "object"
        )
            return false;

        const identifier = String(record.actionId);

        if (identifier.length === 0)
            return false;

        // The dialog lives in the workspace; with no workspace there is
        // nothing to present it in and nothing is armed.
        if (!surfaces.workspaceOpen)
            return false;

        surfaces.confirmation = {
            "open": true,
            "submitted": false,
            "kind": String(record.kind),
            "actionId": identifier,
            "targetId": String(record.targetId),
            "targetName": String(record.targetName),
            "title": String(record.title),
            "consequence": String(record.consequence),
            "confirmLabel": String(record.confirmLabel),
            "requiresName": record.requiresName === true,
            "generation":
                typeof record.generation === "number"
                ? record.generation
                : -1,
            "originView": surfaces.workspaceView,
            "originSubpage": surfaces.subpage
        };

        return true;
    }

    function cancelConfirmation() {
        if (surfaces.confirmation === null)
            return;

        surfaces.confirmation = null;
        surfaces.confirmationCancelled();
    }

    // Execution reads the captured record and immediately spends it, so a
    // repeated activation cannot submit the same operation twice.
    function submitConfirmation() {
        const record = surfaces.confirmation;

        if (
            record === null
            || record.open !== true
            || record.submitted === true
        )
            return null;

        surfaces.confirmation = null;
        return record;
    }

    // Any change that could move the target under the dialog invalidates it.
    function invalidateConfirmation(generation) {
        const record = surfaces.confirmation;

        if (record === null)
            return;

        const current =
            typeof generation === "number" ? generation : -1;

        if (
            record.generation >= 0
            && current >= 0
            && record.generation !== current
        ) {
            surfaces.cancelConfirmation();
            return;
        }

        if (
            record.originView !== surfaces.workspaceView
            || record.originSubpage !== surfaces.subpage
            || !surfaces.workspaceOpen
        ) {
            surfaces.cancelConfirmation();
        }
    }
}
