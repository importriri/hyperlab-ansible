#!/usr/bin/env bash
set -euo pipefail

mode="${1:-full}"
choose="${2:-archive}"
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
pictures_dir="$(xdg-user-dir PICTURES 2>/dev/null || true)"
if [[ -z ${pictures_dir} || ${pictures_dir} != /* ]]; then
    pictures_dir="${HOME}/Pictures"
fi
archive_dir="${pictures_dir}/Screenshots"
mkdir -p -- "${archive_dir}"

tmp="$(mktemp --tmpdir="${runtime_dir}" hyperlab-screenshot.XXXXXX.png)"
cleanup() {
    rm -f -- "${tmp}"
}
trap cleanup EXIT

case "${mode}" in
    full)
        grim "${tmp}"
        ;;
    region)
        geometry="$(slurp)" || exit 0
        grim -g "${geometry}" "${tmp}"
        ;;
    *)
        printf 'usage: %s [full|region] [archive|choose]\n' "$0" >&2
        exit 2
        ;;
esac

timestamp="$(date '+%Y%m%d-%H%M%S')"
default_target="${archive_dir}/HyperLab-${timestamp}.png"
if [[ -e ${default_target} ]]; then
    default_target="${archive_dir}/HyperLab-${timestamp}-$$.png"
fi

target="${default_target}"
if [[ ${choose} == choose ]]; then
    target="$(printf '%s\n' "${default_target}" | rofi -dmenu -p 'Save screenshot as')"
    [[ -n ${target} ]] || exit 0
    if [[ ${target} != /* ]]; then
        target="${HOME}/${target}"
    fi
    [[ ${target} == *.png ]] || target="${target}.png"
    mkdir -p -- "$(dirname -- "${target}")"
elif [[ ${choose} != archive ]]; then
    printf 'usage: %s [full|region] [archive|choose]\n' "$0" >&2
    exit 2
fi

install -m 0600 -- "${tmp}" "${target}"
wl-copy --type image/png <"${tmp}"
printf '%s\n' "${target}"
