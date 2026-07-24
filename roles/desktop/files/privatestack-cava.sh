#!/usr/bin/env bash
# Bridge cava's raw ascii output into a waybar custom module.
#
# cava prints one line per frame: N values 0-7 separated by ';'. sed -u
# (unbuffered) rewrites them into eighth-block glyphs and hands the line
# straight to waybar, which reads this script as a stream.
#
# Only instances started from THIS config are killed: an interactive cava
# in a terminal keeps running.
set -euo pipefail

declare -r config="${HOME}/.config/cava/cava-waybar.conf"

if [[ ! -r ${config} ]]; then
    echo "cava config not readable: ${config}" >&2
    exit 1
fi

# waybar restarts the script on reload; reap the previous stream first.
pkill -x -f "cava -p ${config}" >/dev/null 2>&1 || true

exec cava -p "${config}" \
    | sed -u 's/;//g; s/0/▁/g; s/1/▂/g; s/2/▃/g; s/3/▄/g; s/4/▅/g; s/5/▆/g; s/6/▇/g; s/7/█/g'
