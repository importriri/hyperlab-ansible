#!/usr/bin/env bash
# Group 16: the rebuilt Looking Glass sender and the stream health (A5,
# ADR 0045) on dev-01. The guest profile playbook asks for the guest
# account's password itself, once; the host password is never used here.
export ACCEPTANCE_GROUP=16-looking-glass-sender
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start

inventory=(-i inventory.ini -i "${XDG_RUNTIME_DIR}/dev-01.ini")
backup "sender binary checksum before" ansible dev-01 "${inventory[@]}" -m command \
    -a "sha256sum /usr/local/bin/looking-glass-host"
rollback "rebuild from the previous commit's patch (the role keys the build on the patch digest)"

report "The profile playbook rebuilds the sender; it asks for the guest password itself."
log="$EVIDENCE/profile-playbook.log"
(cd "$ACCEPTANCE_REPO" && ANSIBLE_LOG_PATH="$log.raw" ansible-playbook -K "${inventory[@]}" \
    playbooks/guest-arch-dev-vfio.yml)
rc=$?
redact <"$log.raw" >"$log" && rm -f -- "$log.raw"
if (( rc == 0 )); then PASSES=$((PASSES + 1)); report "PASS  profile playbook"; else
    FAILS=$((FAILS + 1)); report "FAIL  profile playbook (evidence: $log)"; fi

check "stream health answers" "$ACCEPTANCE_REPO/tools/hyperlabctl/bin/hyperlabctl" --json looking-glass health dev-01
report "Open Looking Glass on dev-01 and leave the desktop still for two minutes."
ask "two still minutes passed" "Have two minutes passed with the client open and the desktop still?"
check "no stall on a still desktop" ansible dev-01 "${inventory[@]}" -m shell \
    -a "! grep -q 'No usable frame' ~/.local/state/hyperlab/looking-glass-host.log"
check "health is ok" "$ACCEPTANCE_REPO/tools/hyperlabctl/bin/hyperlabctl" --json looking-glass health dev-01
expect "health word is ok" '"health":"ok"' "$ACCEPTANCE_REPO/tools/hyperlabctl/bin/hyperlabctl" --json looking-glass health dev-01
report "Press SUPER+SHIFT+L in a dev-01 terminal through Looking Glass."
ask "no 8;10u in the terminal" "Is there NO '8;10u' at the prompt?"
screenshot "dev-01 terminal after SUPER+SHIFT+L"
report "From the Machine pane, use Restart capture once."
ask "capture restarted, guest kept running" "Did the picture come back within seconds, with dev-01 still running?"
acceptance_end
