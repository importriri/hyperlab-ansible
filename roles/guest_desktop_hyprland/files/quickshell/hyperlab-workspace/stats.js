// Pure parsers for the status island. Every number the island shows comes
// from one of these sources inside the guest; a source that cannot be read
// yields null and the island hides the readout instead of inventing one.

.pragma library

// /proc/stat aggregate line -> {busy, total} jiffies.
function cpuSample(text) {
    const line = String(text).split("\n").find(row => row.startsWith("cpu "));
    if (!line)
        return null;
    const fields = line.trim().split(/\s+/).slice(1).map(Number);
    if (fields.length < 4 || fields.some(value => !Number.isFinite(value)))
        return null;
    const idle = fields[3] + (fields[4] || 0);
    const total = fields.reduce((sum, value) => sum + value, 0);
    return { "busy": total - idle, "total": total };
}

// Percentage between two samples, or null when there is no interval yet.
function cpuPercent(previous, current) {
    if (!previous || !current)
        return null;
    const total = current.total - previous.total;
    const busy = current.busy - previous.busy;
    if (total <= 0 || busy < 0)
        return null;
    return Math.max(0, Math.min(100, Math.round(busy * 100 / total)));
}

// /proc/meminfo -> {usedGiB, totalGiB}.
function memory(text) {
    const values = {};
    String(text).split("\n").forEach(row => {
        const match = row.match(/^(\w+):\s+(\d+)\s+kB/);
        if (match)
            values[match[1]] = Number(match[2]);
    });
    if (!values.MemTotal || values.MemAvailable === undefined)
        return null;
    const kib = 1024 * 1024;
    return {
        "usedGiB": (values.MemTotal - values.MemAvailable) / kib,
        "totalGiB": values.MemTotal / kib
    };
}

function memoryText(sample) {
    if (!sample)
        return "";
    return sample.usedGiB.toFixed(1) + " / " + sample.totalGiB.toFixed(1) + " G";
}

// /proc/net/route -> name of the interface holding the default route.
function defaultInterface(text) {
    const rows = String(text).split("\n").slice(1);
    for (let i = 0; i < rows.length; i++) {
        const fields = rows[i].trim().split(/\s+/);
        if (fields.length >= 8 && fields[1] === "00000000" && fields[7] === "00000000")
            return fields[0];
    }
    return "";
}

// `nvidia-smi --query-gpu=utilization.gpu,temperature.gpu
//  --format=csv,noheader,nounits` -> {load, temperature} of the first GPU.
function gpu(text) {
    const line = String(text).split("\n").find(row => row.trim().length > 0);
    if (!line)
        return null;
    const fields = line.split(",").map(field => Number(field.trim()));
    if (fields.length < 2 || !Number.isFinite(fields[0]))
        return null;
    return {
        "load": Math.max(0, Math.min(100, Math.round(fields[0]))),
        "temperature": Number.isFinite(fields[1]) ? Math.round(fields[1]) : null
    };
}

// Keep a fixed-length history for the CPU trace.
function pushHistory(history, value, length) {
    const next = history.slice(Math.max(0, history.length - length + 1));
    next.push(value);
    return next;
}
