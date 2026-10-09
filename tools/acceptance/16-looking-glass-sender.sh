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

# pid_now: the running sender's pid, or nothing.
pid_now() {
    probe 2>/dev/null | sed -n 's/^pid=\([0-9][0-9]*\)$/\1/p' | head -n 1
}

# health_ok: PASS only on the word "ok", within 30 seconds.
health_ok() {
    local answer
    for _ in 1 2 3 4 5 6; do
        answer=$("$HYPERLABCTL" --json looking-glass health dev-01 2>&1)
        if grep -q '"health":"ok"' <<<"$answer"; then
            printf '%s\n' "$answer"
            return 0
        fi
        sleep 5
    done
    printf '%s\n' "$answer"
    return 1
}
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

if (( go )); then
    go=0
    tested=$(pid_now)
    report "Open Looking Glass on dev-01 and leave the desktop still for two minutes."
    ask "two still minutes passed with dev-01's desktop shown" \
        "Have two minutes passed with dev-01's desktop (not the waiting logo) shown and still?"
    if check "health is ok" health_ok \
        && identity "same sender, no capture restart on a still desktop" --since "$started" --pid "${tested:-none}" --no-restart; then
        go=1
    fi
fi

if (( go )); then
    go=0
    report "Press SUPER+SHIFT+L in a dev-01 terminal through Looking Glass."
    ask "no 8;10u in the terminal" "Is there NO '8;10u' at the prompt?"
    screenshot "dev-01 terminal after SUPER+SHIFT+L"
    before=$(pid_now)
    if confirm pane "use Restart capture once from the Machine pane now: dev-01's stream stops for a few seconds"; then
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
