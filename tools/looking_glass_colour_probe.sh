#!/usr/bin/env bash
# looking_glass_colour_probe.sh - read-only check of how the host Looking Glass
# client describes guest frames to the compositor.
#
# Starts a second, input-less client for a few seconds with the Wayland
# protocol trace on. It does not touch SPICE, the running client or the guest.
# A colour-managed surface tagged ST2084 PQ (tf 11) / BT.2020 (primaries 6)
# while the host output is SDR is the regression in
# problems/looking-glass-linux-sdr-flagged-hdr.md.
set -euo pipefail

client=/usr/local/bin/looking-glass-client
seconds="${1:-6}"
log="$(mktemp)"
trap 'rm -f -- "${log}"' EXIT

[ -x "${client}" ] || { echo "RESULT=BLOCKED reason=client-missing"; exit 2; }
[ -n "${WAYLAND_DISPLAY:-}" ] || { echo "RESULT=BLOCKED reason=no-wayland-session"; exit 2; }

WAYLAND_DEBUG=client timeout "${seconds}" "${client}" \
    app:shmFile=/dev/kvmfr0 spice:enable=no win:title="HyperLab colour probe" \
    >"${log}" 2>&1 || true

echo "== host output"
if command -v hyprctl >/dev/null 2>&1; then
    hyprctl monitors 2>/dev/null \
        | grep -E '^Monitor|currentFormat|colorManagementPreset|sdrMaxLuminance' || true
fi
echo "== client frame/HDR log"
grep -iE 'format|hdr|tone' "${log}" | grep -v 'wp_\|wl_\|xdg_' | head -n 20 || true
echo "== colour-management requests"
grep -E 'set_tf_named|set_primaries_named|set_image_description|get_surface' "${log}" \
    | sed -E 's/^\[[^]]*\] *//' | head -n 20 || true

frame="$(grep -Eo 'Format: FRAME_TYPE_[A-Z0-9_]+ .* hdr:[01] pq:[01]' "${log}" | tail -n1 || true)"
echo "== last received frame: ${frame:-none}"

if grep -Eq 'set_tf_named\([^)]*\b11\)' "${log}"; then
    echo "RESULT=FAIL surface tagged ST2084 PQ"
    exit 1
fi
if [ -z "${frame}" ]; then
    # No frame means no evidence either way: an absent PQ request proves nothing.
    echo "RESULT=INCONCLUSIVE no guest frame received"
    exit 3
fi
case "${frame}" in
    *"hdr:0 pq:0") echo "RESULT=PASS SDR frame, no PQ surface description" ;;
    *) echo "RESULT=FAIL sender still flags the frame HDR: ${frame}"; exit 1 ;;
esac
