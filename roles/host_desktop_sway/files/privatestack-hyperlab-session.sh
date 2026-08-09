#!/usr/bin/env bash
set -u
set -o pipefail

readonly manager=${PRIVATESTACK_HYPERLAB_MANAGER:-/usr/local/bin/privatestack-hyperlab-domains}
readonly app_id=${PRIVATESTACK_HYPERLAB_APP_ID:-io.github.importriri.HyperlabControlCenter}
readonly runtime_dir=${XDG_RUNTIME_DIR:-/tmp}
readonly restart_lock=${runtime_dir}/privatestack-hyperlab-session.lock

find_manager_pids() {
    local proc cmdline

    for proc in /proc/[0-9]*; do
        [[ -r "${proc}/cmdline" ]] || continue
        { cmdline=$(tr '\0' ' ' <"${proc}/cmdline"); } 2>/dev/null || continue

        case " ${cmdline} " in
            *" ${manager} "*) printf '%s\n' "${proc##*/}" ;;
        esac
    done
}

wait_for_manager_exit() {
    local attempt
    local -a pids

    for ((attempt = 0; attempt < 100; attempt++)); do
        mapfile -t pids < <(find_manager_pids)
        (( ${#pids[@]} == 0 )) && return 0
        sleep 0.05
    done

    return 1
}

exec 9>"${restart_lock}"
flock -n 9 || exit 0

# Sway runs this helper through exec_always. Replace the resident application
# on every reload so a newly deployed Python manager cannot forward requests to
# an older process that still has the previous source loaded in memory.
gapplication action "${app_id}" quit >/dev/null 2>&1 || true

if ! wait_for_manager_exit; then
    mapfile -t manager_pids < <(find_manager_pids)
    (( ${#manager_pids[@]} == 0 )) || kill -TERM "${manager_pids[@]}"
    wait_for_manager_exit || {
        printf 'HyperLab manager did not stop; refusing a duplicate instance\n' >&2
        exit 1
    }
fi

flock -u 9
exec 9>&-
exec "${manager}" --warm
