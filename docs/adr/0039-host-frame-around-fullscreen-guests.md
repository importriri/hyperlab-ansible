# ADR 0039 - The host frame around a fullscreen guest window

Status: proposed. The operator chooses; today the provenance colour is the
focused window's border, which fullscreen hides.

## Context

Roadmap milestone 11 asks that every focused surface be named by the host,
fullscreen guests included, and that the host frame stay visible around a
Looking Glass window at all times. The resolver already names a surface the
same way whether it is fullscreen or not: it answers for the focused PID and
window. What disappears is the presentation: the host shows provenance as
the focused window's border colour and in the top rail, and a fullscreen
window covers the rail and has no border. A guest that is fullscreen can
therefore draw anything, including a fake host desktop, with nothing
host-drawn on screen to contradict it.

## Options

**A. A host-drawn ring on the overlay layer (recommended).** While the
focused surface is a guest and is fullscreen, the host shell draws a thin
ring in that guest's provenance colour around the output, on the
compositor's overlay layer, above every window, with an empty input region
so it takes no clicks. It is drawn by the host from the resolver's answer,
never by the guest, and it disappears with the fullscreen state or the
focus. It covers a few pixels of the guest's edge.

**B. No true fullscreen for guest windows.** The host fullscreen key
maximizes a guest window instead, keeping its border and the rail. Simpler,
and the frame is the usual one, but games and video lose true fullscreen
and the rail's height.

**C. Leave it.** Rejected: the roadmap asks for the frame at all times.

## Recommendation

A, with the ring's width a design token, so the frame holds in fullscreen
without changing how fullscreen behaves. The ring must be checked on Nitro
over a fullscreen Looking Glass window and over a fullscreen SPICE console.
