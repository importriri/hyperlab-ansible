// Which transient surface is open. At most one holds the keyboard at a
// time: opening the launcher closes the overview and the other way round.

import QtQuick

QtObject {
    id: surfaces

    property bool launcherOpen: false
    property bool overviewOpen: false
    property bool cheatsheetOpen: false
    // Set when the overview should start with the new-project field open.
    property int newProjectSerial: 0

    function openLauncher() {
        overviewOpen = false;
        cheatsheetOpen = false;
        launcherOpen = true;
    }

    function toggleLauncher() {
        if (launcherOpen)
            closeAll();
        else
            openLauncher();
    }

    function openOverview() {
        launcherOpen = false;
        cheatsheetOpen = false;
        overviewOpen = true;
    }

    function toggleCheatsheet() {
        const wasOpen = cheatsheetOpen;
        closeAll();
        cheatsheetOpen = !wasOpen;
    }

    function toggleOverview() {
        if (overviewOpen)
            closeAll();
        else
            openOverview();
    }

    function newProject() {
        openOverview();
        newProjectSerial += 1;
    }

    function closeAll() {
        launcherOpen = false;
        overviewOpen = false;
        cheatsheetOpen = false;
    }
}
