#!/usr/bin/env bash
# Group 16: the rebuilt Looking Glass sender and the stream health (A5,
# ADR 0045) on dev-01. dev-01 is not an hl-lab-* Machine: the rebuild and
# every restart of its sender stop for a typed confirmation that says what
# they do. Fail closed: a failed step ends the group before any question to
# the operator, so nobody answers in front of the waiting logo. The host
# password is never used here; the playbook asks for dev-01's own.
export ACCEPTANCE_GROUP=16-looking-glass-sender
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start

HYPERLABCTL=${HYPERLABCTL:-$ACCEPTANCE_REPO/tools/hyperlabctl/bin/hyperlabctl}
IDENTITY="$ACCEPTANCE_REPO/tools/acceptance/sender_identity.py"
PHASES="$ACCEPTANCE_REPO/tools/acceptance/sender_phases.py"
# The still phase is timed here; the judge refuses one shorter than 5
# minutes measured inside dev-01, so a shorter wait only fails.
STILL_SECONDS=${ACCEPTANCE_STILL_SECONDS:-300}
inventory=(-i inventory.ini -i "${XDG_RUNTIME_DIR}/dev-01.ini")

# probe: what the sender running in dev-01 is, read without changing it.
probe() {
    (cd "$ACCEPTANCE_REPO" && ansible dev-01 "${inventory[@]}" -m shell \
        -a "$(python3 "$IDENTITY" --print-probe)")
}

# identity NAME ARGS...: PASS only when the running sender is this build.
identity() {
    local name=$1 read
    shift
    read="$EVIDENCE/probe-$(slug "$name").txt"
    probe >"$read" 2>&1
    check "$name" python3 "$IDENTITY" --input "$read" "$@"
}

# in_dev01 SCRIPT FILE: run one of sender_phases.py's scripts in dev-01.
in_dev01() {
    (cd "$ACCEPTANCE_REPO" && ansible dev-01 "${inventory[@]}" -m shell \
        -a "$(python3 "$PHASES" "$1")") >"$2" 2>&1
}

# pid_now: the running sender's pid, or nothing.
pid_now() {
    probe 2>/dev/null | sed -n 's/^pid=\([0-9][0-9]*\)$/\1/p' | head -n 1
}

# health_ok [SECONDS]: PASS only on the word "ok", within SECONDS (30 by
# default). "idle" means no Looking Glass client is subscribed to the sender,
# which then logs Capture Stop and waits; the client meanwhile shows dev-01's
# SPICE display, which looks like the stream. A failure says so.
health_ok() {
    local answer limit=${1:-30} waited=0
    while :; do
        answer=$("$HYPERLABCTL" --json looking-glass health dev-01 2>&1)
        if grep -q '"health":"ok"' <<<"$answer"; then
            printf '%s\n' "$answer"
            return 0
        fi
        (( waited >= limit )) && break
        sleep 5
        waited=$((waited + 5))
    done
    printf '%s\n' "$answer"
    if grep -q '"health":"idle"' <<<"$answer"; then
        printf '%s\n' "$NO_CLIENT"
    fi
    return 1
}
NO_CLIENT="no Looking Glass client is connected to dev-01's sender (health idle: its log ends with Capture Stop); a window showing dev-01 is the client's SPICE display, not the stream"
backup "sender before" probe
rollback "the role keys the build on the patch digests: rebuild from the previous commit with the same playbook"
started=$(date +%s)
go=0

if confirm rebuild "apply playbooks/guest-looking-glass-linux.yml to dev-01 (not an hl-lab-* Machine): it builds and installs the Looking Glass sender from the reviewed patches and the pinned kvmfr module for the running kernel. It never upgrades packages or the kernel, and refuses if the running kernel has no build tree. It asks for dev-01's password."; then
    log="$EVIDENCE/sender-playbook.log"
    (cd "$ACCEPTANCE_REPO" && ANSIBLE_LOG_PATH="$log.raw" ansible-playbook -K "${inventory[@]}" \
        playbooks/guest-looking-glass-linux.yml)
    rc=$?
    redact <"$log.raw" >"$log" && rm -f -- "$log.raw"
    if (( rc == 0 )); then
        PASSES=$((PASSES + 1))
        report "PASS  sender playbook"
        go=1
    else
        FAILS=$((FAILS + 1))
        report "FAIL  sender playbook (full log: $log)"
        failed_tasks "$log" | tee -a "$REPORT" >&2
    fi
fi

if (( go )); then
    go=0
    before=$(pid_now)
    if confirm restart "restart the sender in dev-01 (not an hl-lab-* Machine) so the new build runs: the stream stops for a few seconds"; then
        restarted=$(date +%s)
        if check "capture restarted from the host" "$HYPERLABCTL" looking-glass restart-capture dev-01 \
            && identity "the running sender is this build, started for this test" \
                --since "$restarted" --not-pid "${before:-none}"; then
            go=1
        fi
    fi
fi

# The operator's criterion (2026-10-11): one sender of this build for both
# phases, no "restarting the capture" since it started and no "Capture Stop"
# since the still phase began; still for 5 minutes, warnings allowed and
# counted; then the screen changes, with no warning and, if a warning was
# active, "Frames resumed" within 2 s. tools/acceptance/sender_phases.py
# judges it from the sender's log, on dev-01's clock.
if (( go )); then
    go=0
    report "Open Looking Glass on dev-01 and show its desktop. This script waits up to 60 s for dev-01's sender to stream to it; from then on, touch neither dev-01 nor its window until this script says so."
    # The stream first, then the operator: a window can show dev-01 through
    # SPICE with no client connected to the sender.
    if ! check "health is ok before the still phase" health_ok 60; then
        grep -Fx "$NO_CLIENT" "$EVIDENCE/health-is-ok-before-the-still-phase.log" | sed 's/^/      /' \
            | tee -a "$REPORT" >&2
    elif before=$FAILS && ask "Looking Glass shows dev-01's desktop" \
            "Does Looking Glass show dev-01's desktop (not the waiting logo)?" && (( FAILS == before )); then
        tested=$(pid_now)
        in_dev01 mark "$EVIDENCE/phase-still-start.txt"
        report "Still phase: $STILL_SECONDS s, timed by this script. Do not touch dev-01 or its window."
        sleep "$STILL_SECONDS"
        in_dev01 mark "$EVIDENCE/phase-still-end.txt"
        report "Changing phase: dev-01 now shows a notification with its time every second for 30 s; each closes by itself."
        in_dev01 change "$EVIDENCE/phase-change.txt"
        in_dev01 log "$EVIDENCE/phase-log.txt"
        if check "still and changing phases" python3 "$PHASES" judge --start "$EVIDENCE/phase-still-start.txt" \
                --end "$EVIDENCE/phase-still-end.txt" --change "$EVIDENCE/phase-change.txt" \
                --log "$EVIDENCE/phase-log.txt" \
            && check "health is ok after the changing phase" health_ok \
            && identity "the same sender of this build, no capture restart since it started" \
                --since "$started" --pid "${tested:-none}" --no-restart; then
            go=1
        fi
        grep -E '^note  opened' "$EVIDENCE/still-and-changing-phases.log" | sed 's/^note  /      /' | tee -a "$REPORT" >&2
    fi
fi

if (( go )); then
    go=0
    report "Press SUPER+SHIFT+L in a dev-01 terminal through Looking Glass."
    ask "no 8;10u in the terminal" "Is there NO '8;10u' at the prompt?"
    screenshot "dev-01 terminal after SUPER+SHIFT+L"
    before=$(pid_now)
    # The button comes with ADR 0045's shell; a host whose installed shell
    # is older has no button, and that is not the sender's failure.
    offered "Restart capture from the pane" "Does dev-01's Machine pane offer Restart capture?" \
        "the Machine pane does not offer it; the installed shell may predate ADR 0045 (check that the host desktop playbook ran from this commit)"
    pane_offered=$?
    if (( pane_offered == 1 )); then
        go=1
    elif (( pane_offered == 0 )) && confirm pane "use Restart capture once from the Machine pane now: dev-01's stream stops for a few seconds"; then
        report "Use Restart capture on dev-01's Machine pane, then come back here."
        pane=$(date +%s)
        ask "Restart capture used once from the pane" "Did you use Restart capture once on dev-01's pane?"
        if identity "the pane's restart left a new sender with its own start line" \
            --since "$pane" --not-pid "${before:-none}" \
            && check "health is ok after the pane's restart" health_ok; then
            go=1
        fi
    fi
fi

if (( ! go )); then
    report "STOPPED at the first failed or skipped step: no later question was asked."
fi
acceptance_end
