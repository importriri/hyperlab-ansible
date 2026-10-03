// Pure Desk and project logic for the HyperLab Workspace Shell.
//
// Mirrors hyperlab-desk: Desk d owns workspaces d*10+1..d*10+9 and slot s
// of that Desk is workspace d*10+s. Nothing here talks to a process or the
// compositor, so every rule can be exercised with plain fixtures.

.pragma library

function split(workspace) {
    const id = Number(workspace);
    if (!Number.isInteger(id))
        return null;
    const desk = Math.floor(id / 10);
    const slot = id % 10;
    if (desk >= 1 && desk <= 9 && slot >= 1 && slot <= 9)
        return { "desk": desk, "slot": slot };
    return null;
}

function workspaceOf(desk, slot) {
    return desk * 10 + slot;
}

function deskAt(model, index) {
    const desks = model && Array.isArray(model.desks) ? model.desks : [];
    return index >= 1 && index <= desks.length ? desks[index - 1] : null;
}

function projectAt(desk, slot) {
    if (!desk || !Array.isArray(desk.projects))
        return null;
    for (let i = 0; i < desk.projects.length; i++) {
        if (desk.projects[i].slot === slot)
            return desk.projects[i];
    }
    return null;
}

// Where the active workspace sits, in words the shell can show.
function place(model, workspace) {
    const position = split(workspace);
    const desk = position ? deskAt(model, position.desk) : null;
    const project = desk ? projectAt(desk, position.slot) : null;
    return {
        "desk": position ? position.desk : 0,
        "slot": position ? position.slot : 0,
        "deskName": desk ? desk.name : "",
        "projectName": project ? project.name : "",
        "label": project ? project.name
               : (position ? "Workspace " + position.slot : "Workspace " + workspace)
    };
}

function windowsText(count) {
    if (count <= 0)
        return "closed";
    return count === 1 ? "1 window" : count + " windows";
}

// The workspace dots of one Desk: every slot that has a project, has
// windows, or is active, in slot order.
function slots(model, deskIndex, counts, activeWorkspace) {
    const desk = deskAt(model, deskIndex);
    const result = [];
    for (let slot = 1; slot <= 9; slot++) {
        const id = workspaceOf(deskIndex, slot);
        const windows = counts[id] || 0;
        const project = projectAt(desk, slot);
        const active = id === activeWorkspace;
        if (active || windows > 0 || project) {
            result.push({
                "slot": slot,
                "workspace": id,
                "windows": windows,
                "active": active,
                "name": project ? project.name : "Workspace " + slot
            });
        }
    }
    return result;
}

// Windows on a Desk across all its slots.
function deskWindows(deskIndex, counts) {
    let total = 0;
    for (let slot = 1; slot <= 9; slot++)
        total += counts[workspaceOf(deskIndex, slot)] || 0;
    return total;
}

// Rows for the Desks overview card.
function projectRows(model, deskIndex, counts, activeWorkspace) {
    const desk = deskAt(model, deskIndex);
    if (!desk)
        return [];
    return desk.projects.map(project => {
        const id = workspaceOf(deskIndex, project.slot);
        const windows = counts[id] || 0;
        return {
            "slot": project.slot,
            "name": project.name,
            "cwd": project.cwd,
            "windows": windows,
            "meta": windowsText(windows),
            "active": id === activeWorkspace
        };
    });
}

// Hyprland's workspace list to {id: windows}; tolerant of partial objects.
function countsFrom(workspaces) {
    const counts = {};
    for (let i = 0; i < workspaces.length; i++) {
        const item = workspaces[i];
        if (!item)
            continue;
        const id = Number(item.id);
        const ipc = item.lastIpcObject || {};
        const windows = Number(ipc.windows);
        if (Number.isInteger(id))
            counts[id] = Number.isFinite(windows) && windows > 0 ? windows : 0;
    }
    return counts;
}

// Parse `hyperlab-desk model` output. An unreadable reply is an error the
// shell shows, never an empty machine.
function parseModel(text) {
    let data;
    try {
        data = JSON.parse(String(text));
    } catch (error) {
        return { "ok": false, "error": "The Desk helper returned unreadable output." };
    }
    if (!data || !Array.isArray(data.desks) || data.desks.length === 0)
        return { "ok": false, "error": "The Desk helper returned no Desks." };
    for (let i = 0; i < data.desks.length; i++) {
        const desk = data.desks[i];
        if (!desk || typeof desk.name !== "string" || !Array.isArray(desk.projects))
            return { "ok": false, "error": "The Desk helper returned a malformed Desk." };
    }
    return {
        "ok": true,
        "model": data,
        "errors": Array.isArray(data.errors) ? data.errors.map(String) : []
    };
}
