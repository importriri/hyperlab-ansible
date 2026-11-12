// One Machine, drawn as a sphere (ADR 0064).
//
// A running Machine is a lit sphere tinted with its domain colour; state is
// carried by shape and light, never by colour alone. Identity and state are
// host-confirmed inputs: this component observes nothing, performs nothing
// and changes only when its caller reports a confirmed fact.
//
// Colours come only from Theme.provenanceColor() and the appearance text
// tone; none is written here. An external domain, an unresolved identity or
// a state outside the reviewed vocabulary is a neutral outline without fill,
// never a domain colour or the HOST grey.

import QtQuick

Item {
    id: sphere

    required property var theme
    required property var tokens

    property string machineName: ""
    property string domain: ""
    // Item.state carries the Machine state. The component declares no QML
    // States, so nothing but the caller ever changes it.
    state: ""
    property bool disposable: false
    property bool gpuOwner: false
    property int size: 32

    readonly property var drawnStates: [
        "running", "shut off", "starting", "stopping", "paused", "suspended"
    ]
    readonly property bool knownDomain:
        sphere.theme.provenanceAvailable && sphere.theme.knownProvenance(sphere.domain)
    readonly property bool knownState: sphere.drawnStates.indexOf(sphere.state) >= 0
    readonly property bool classified: sphere.knownDomain && sphere.knownState
    readonly property bool lit: sphere.classified && sphere.state === "running"
    readonly property bool paused:
        sphere.classified && (sphere.state === "paused" || sphere.state === "suspended")
    readonly property bool transitioning:
        sphere.classified && (sphere.state === "starting" || sphere.state === "stopping")
    readonly property bool reducedMotion: sphere.tokens.reducedMotion
    readonly property color tone:
        sphere.classified ? sphere.theme.provenanceColor(sphere.domain)
                          : sphere.theme.textPrimary

    // The word a surface writes beside the sphere.
    readonly property string domainWord:
        sphere.state === "external" ? "external"
        : sphere.knownDomain && sphere.state !== "unclassified" ? String(sphere.domain).toLowerCase()
        : "unclassified"

    // Proportions of `size`. Everything, rings and token included, stays
    // inside 0.5: nothing is drawn beyond the sphere's own envelope.
    readonly property real bodyRatio: 0.37
    readonly property real orbitRatio: 0.43
    property real phase: 0

    implicitWidth: sphere.size
    implicitHeight: sphere.size
    width: sphere.size
    height: sphere.size

    Accessible.role: Accessible.Graphic
    Accessible.name: (sphere.machineName.length > 0 ? sphere.machineName : "Machine")
        + ", " + sphere.domainWord
        + ", " + (sphere.state.length > 0 ? sphere.state : "unknown")
        + (sphere.disposable ? ", disposable" : "")
        + (sphere.gpuOwner ? ", owns the GPU" : "")

    // Moves only while the caller reports a transition; never ambient.
    NumberAnimation on phase {
        from: 0
        to: 1
        duration: 1200
        loops: Animation.Infinite
        running: sphere.transitioning && !sphere.reducedMotion && sphere.visible
    }

    onToneChanged: paint.requestPaint()
    onStateChanged: paint.requestPaint()
    onClassifiedChanged: paint.requestPaint()
    onDisposableChanged: paint.requestPaint()
    onGpuOwnerChanged: paint.requestPaint()
    onSizeChanged: paint.requestPaint()
    onReducedMotionChanged: paint.requestPaint()
    onPhaseChanged: {
        if (sphere.transitioning && !sphere.reducedMotion)
            paint.requestPaint();
    }

    Canvas {
        id: paint

        anchors.fill: parent
        antialiasing: true

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            ctx.clearRect(0, 0, width, height);

            const cx = width / 2;
            const cy = height / 2;
            const r = sphere.size * sphere.bodyRatio;
            const orbit = sphere.size * sphere.orbitRatio;
            const rim = Math.max(1, sphere.size * 0.03);
            const tone = sphere.tone;

            // Body. Light from the upper left, darker lower right. A shut-off
            // or transitioning Machine is dark; a paused one is dimmed.
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, 2 * Math.PI);
            if (sphere.classified) {
                const dim = sphere.lit ? 1 : sphere.paused ? 2.6 : 9;
                const light = ctx.createRadialGradient(
                    cx - r * 0.38, cy - r * 0.42, 0, cx, cy, r);
                light.addColorStop(0, Qt.darker(Qt.lighter(tone, 1.3), dim));
                light.addColorStop(0.42, Qt.darker(tone, 1.3 * dim));
                light.addColorStop(0.82, Qt.darker(tone, 3.4 * dim));
                light.addColorStop(1, Qt.darker(tone, 2.2 * dim));
                ctx.fillStyle = light;
                ctx.fill();
            }

            // Rim: the domain colour, or the neutral outline when there is
            // no confirmed identity and state.
            ctx.lineWidth = rim;
            ctx.strokeStyle = tone;
            ctx.stroke();

            // Specular highlight, a filled disc well inside the body.
            if (sphere.lit || sphere.paused) {
                const hx = cx - r * 0.36;
                const hy = cy - r * 0.40;
                const hr = r * 0.30;
                const shine = ctx.createRadialGradient(hx, hy, 0, hx, hy, hr);
                shine.addColorStop(0, sphere.theme.alpha(Qt.lighter(tone, 1.8),
                                                         sphere.paused ? 0.15 : 0.65));
                shine.addColorStop(1, sphere.theme.alpha(tone, 0));
                ctx.beginPath();
                ctx.arc(hx, hy, hr, 0, 2 * Math.PI);
                ctx.fillStyle = shine;
                ctx.fill();
            }

            // Pause notch: two cuts through the top of the silhouette, so
            // pause reads by shape even in monochrome and at 12 px. The cuts
            // sit on whole pixels so they stay two cuts at every size.
            if (sphere.paused) {
                const notch = Math.max(1, Math.round(r * 0.22));
                const gap = Math.max(1, Math.round(r * 0.20));
                const left = Math.round(cx - notch - gap / 2);
                const top = Math.floor(cy - r - rim);
                const depth = Math.ceil(cy - r * 0.42) - top;
                ctx.clearRect(left, top, notch, depth);
                ctx.clearRect(left + notch + gap, top, notch, depth);
            }

            // Transition arc on the orbit. Starting runs clockwise from the
            // top, stopping counter-clockwise; with reduced motion the arc
            // stays fixed at its first position.
            if (sphere.transitioning) {
                const direction = sphere.state === "starting" ? 1 : -1;
                const turn = sphere.reducedMotion ? 0 : sphere.phase;
                const start = -Math.PI / 2 + direction * turn * 2 * Math.PI;
                ctx.beginPath();
                ctx.arc(cx, cy, orbit, start, start + direction * Math.PI * 0.6, direction < 0);
                ctx.strokeStyle = tone;
                ctx.lineWidth = Math.max(1, sphere.size * 0.035);
                ctx.stroke();
            }

            // Disposable: a dashed ring around the sphere, drawn as explicit
            // segments so the software rasteriser draws the same dashes.
            if (sphere.disposable) {
                ctx.strokeStyle = tone;
                ctx.lineWidth = Math.max(1, sphere.size * 0.016);
                for (let index = 0; index < 12; index++) {
                    const angle = index * Math.PI / 6;
                    ctx.beginPath();
                    ctx.arc(cx, cy, orbit, angle, angle + Math.PI / 12);
                    ctx.stroke();
                }
            }

            // GPU token: a small chip with two pins, docked on the ring at
            // the right. It cuts its own gap so it reads on any state.
            if (sphere.gpuOwner) {
                const side = Math.max(2, sphere.size * 0.16);
                const x = cx + orbit - side;
                ctx.clearRect(x - 1, cy - side * 0.8, side + 2, side * 1.6);
                ctx.fillStyle = tone;
                ctx.fillRect(x, cy - side * 0.6, side, side * 1.2);
                const pin = Math.max(0.7, side * 0.15);
                ctx.fillRect(x - side * 0.25, cy - side * 0.4, side * 1.5, pin);
                ctx.fillRect(x - side * 0.25, cy + side * 0.25, side * 1.5, pin);
                ctx.fillStyle = Qt.darker(tone, 5);
                ctx.fillRect(x + side * 0.25, cy - side * 0.3, side * 0.5, side * 0.6);
            }
        }
    }
}
