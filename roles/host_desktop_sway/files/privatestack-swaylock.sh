#!/usr/bin/env bash
set -euo pipefail

image=$(/usr/local/bin/privatestack-theme lock-image)
exec swaylock \
    --config "${XDG_CONFIG_HOME:-${HOME}/.config}/swaylock/config" \
    --image "${image}" \
    --scaling fill \
    "$@"
