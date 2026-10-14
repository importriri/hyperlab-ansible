#!/usr/bin/env bash
# Group 12: the host ring around a fullscreen guest (ADR 0039). Visual: the
# screenshots are reviewed after the run; the operator answers what the eye
# can tell. Nothing here needs root.
export ACCEPTANCE_GROUP=12-fullscreen-ring
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start

report "Open Looking Glass on dev-01 (hyperlabctl open looking-glass dev-01). This script waits up to 60 s for dev-01's sender to stream to it and asks nothing before."
# The stream first, then the operator, as in group 16: with no client on the
# sender the window shows dev-01's SPICE display, and on 2026-10-06 nobody
# could tell afterwards which of the two the answers were about.
if check "health is ok before the ring checks" health_ok 60; then
    report "Press SUPER+F on Looking Glass, then answer."
    ask "ring around the fullscreen guest" "Is there a 4 px ring in dev's colour around the screen?"
    screenshot "fullscreen guest with ring"
    ask "clicks reach the guest at the edges" "Do clicks at the screen edges reach the guest?"
    report "Now make a host terminal (foot) fullscreen."
    ask "no ring for the host" "Is there NO ring around the fullscreen host terminal?"
    screenshot "fullscreen host terminal"
    # ADR 0039 asks for the ring over a fullscreen SPICE console as well: the
    # host names that window from virt-viewer's registered surface, not from
    # Looking Glass.
    report "Leave fullscreen, close Looking Glass (the console and the client use dev-01's one SPICE server), then open dev-01's console (hyperlabctl open console dev-01) and press SUPER+F on it."
    ask "ring around the fullscreen SPICE console" "Is there a 4 px ring in dev's colour around the fullscreen console?"
    screenshot "fullscreen SPICE console with ring"
    report "Leave fullscreen and close the console."
else
    grep -Fx "$NO_CLIENT" "$EVIDENCE/health-is-ok-before-the-ring-checks.log" | sed 's/^/      /' \
        | tee -a "$REPORT" >&2
    report "STOPPED: dev-01's stream is not healthy, so no question was asked."
fi
rollback "systemctl --user restart hyperlab-quickshell.service   (if the ring covers or flickers)"
acceptance_end
