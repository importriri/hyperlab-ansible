#!/usr/bin/env bash
# Group 0: start the nested lab host (ADR 0046) once the host isolates its
# bridge. Run after group 7. The loaded rules are read as root and kept as
# evidence; the lab host starts only after the operator has seen them.
export ACCEPTANCE_GROUP=00-lab-host
# shellcheck source=tools/acceptance/lib.sh disable=SC1091
source "$(dirname "$0")/lib.sh"
acceptance_start
become_once

backup_root "loaded guest isolation input chain" nft list chain inet lab_isolation input
rules="$EVIDENCE/backup-loaded-guest-isolation-input-chain"
if grep -Eq 'iifname "virbr-hl-lab" counter packets [0-9]+ bytes [0-9]+ drop' "$rules" \
        && grep -Eq 'iifname "virbr\*" counter packets [0-9]+ bytes [0-9]+ drop' "$rules"; then
    PASSES=$((PASSES + 1))
    report "PASS  the loaded rules isolate virbr-hl-lab and drop every other virbr* bridge"
    grep -E 'virbr-hl-lab|virbr\*' "$rules" | tee -a "$REPORT" >&2
    rollback "python3 tools/lab/hl_lab.py stop   (or: destroy --yes-remove-hl-lab, only hl-lab-* resources)"
    if confirm start "start hl-lab-testbed and hl-lab-host with the rules above"; then
        check "lab host started" python3 "$ACCEPTANCE_REPO/tools/lab/hl_lab.py" start --isolation-checked
        check "lab host status" python3 "$ACCEPTANCE_REPO/tools/lab/hl_lab.py" status
    fi
else
    FAILS=$((FAILS + 1))
    report "FAIL  the loaded rules do not isolate virbr-hl-lab yet: run group 7 first; nothing started"
fi
acceptance_end
