#!/usr/bin/env bash
# Group 12: the host ring around a fullscreen guest (ADR 0039). Visual: the
# screenshots are reviewed after the run; the operator answers what the eye
# can tell. Nothing here needs root.
export ACCEPTANCE_GROUP=12-fullscreen-ring
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start

report "Open Looking Glass on dev-01 (hyperlabctl open looking-glass dev-01), press SUPER+F on it, then answer."
ask "ring around the fullscreen guest" "Is there a 4 px ring in dev's colour around the screen?"
screenshot "fullscreen guest with ring"
ask "clicks reach the guest at the edges" "Do clicks at the screen edges reach the guest?"
report "Now make a host terminal (foot) fullscreen."
ask "no ring for the host" "Is there NO ring around the fullscreen host terminal?"
screenshot "fullscreen host terminal"
rollback "systemctl --user restart hyperlab-quickshell.service   (if the ring covers or flickers)"
acceptance_end
