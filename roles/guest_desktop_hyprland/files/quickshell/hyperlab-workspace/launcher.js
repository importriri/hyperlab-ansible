// Pure search for the launcher: applications, projects and actions are
// matched and ranked here, so ranking can be tested without a desktop.

.pragma library

// Score how well `query` matches `text`; 0 means no match. Prefix and
// word-start matches outrank scattered subsequences.
function score(query, text) {
    const q = String(query).toLowerCase().trim();
    const t = String(text || "").toLowerCase();
    if (q.length === 0)
        return 1;
    if (t.length === 0)
        return 0;
    if (t.startsWith(q))
        return 1000 - t.length;
    const word = t.indexOf(" " + q);
    if (word >= 0)
        return 800 - word;
    const inner = t.indexOf(q);
    if (inner >= 0)
        return 600 - inner;
    let position = 0;
    let gaps = 0;
    for (let i = 0; i < q.length; i++) {
        const found = t.indexOf(q[i], position);
        if (found < 0)
            return 0;
        gaps += found - position;
        position = found + 1;
    }
    return Math.max(1, 300 - gaps * 5);
}

function bestScore(query, fields) {
    let best = 0;
    for (let i = 0; i < fields.length; i++)
        best = Math.max(best, score(query, fields[i]) - i * 50);
    return best;
}

// Indices into `text` that a query highlights (first contiguous run, else
// the greedy subsequence).
function highlights(query, text) {
    const q = String(query).toLowerCase().trim();
    const t = String(text).toLowerCase();
    if (!q.length)
        return [];
    const at = t.indexOf(q);
    if (at >= 0)
        return Array.from({ "length": q.length }, (_, i) => at + i);
    const marks = [];
    let position = 0;
    for (let i = 0; i < q.length; i++) {
        const found = t.indexOf(q[i], position);
        if (found < 0)
            return [];
        marks.push(found);
        position = found + 1;
    }
    return marks;
}

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

// Rich text with the matched characters in the accent colour.
function marked(query, text, accent) {
    const marks = highlights(query, text);
    const value = String(text);
    let out = "";
    for (let i = 0; i < value.length; i++) {
        const char = escapeHtml(value[i]);
        out += marks.indexOf(i) >= 0
            ? "<font color=\"" + accent + "\">" + char + "</font>"
            : char;
    }
    return out;
}

// Build the result sections. Each entry: {section, kind, title, subtitle,
// hint, payload, score}. Applications and projects are capped so actions
// stay reachable.
function results(query, apps, projects, actions, limits) {
    const q = String(query).trim();
    const appLimit = limits && limits.apps ? limits.apps : 6;
    const projectLimit = limits && limits.projects ? limits.projects : 4;

    const rankedApps = apps
        .map(app => Object.assign({}, app, {
            "score": bestScore(q, [app.title, app.subtitle, app.keywords || ""])
        }))
        .filter(app => app.score > 0)
        .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title))
        .slice(0, q.length ? appLimit : appLimit + 2);

    const rankedProjects = projects
        .map(project => Object.assign({}, project, {
            "score": bestScore(q, [project.title, project.subtitle])
        }))
        .filter(project => project.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, projectLimit);

    const rankedActions = actions
        .filter(action => action.always || (q.length && bestScore(q, [action.title, action.keywords || ""]) > 0));

    const out = [];
    rankedApps.forEach(item => out.push(Object.assign({ "section": "APPLICATIONS" }, item)));
    rankedProjects.forEach(item => out.push(Object.assign({ "section": "PROJECTS" }, item)));
    rankedActions.forEach(item => out.push(Object.assign({ "section": "ACTIONS" }, item)));
    return out;
}

// Index of the first entry of the next section, wrapping.
function nextSection(items, index) {
    if (!items.length)
        return -1;
    const current = items[Math.max(0, index)].section;
    for (let i = index + 1; i < items.length; i++) {
        if (items[i].section !== current)
            return i;
    }
    return 0;
}
