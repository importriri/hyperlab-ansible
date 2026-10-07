# Group 0's "lab host status" passed whatever the state was

Found in the review of the acceptance scripts on 2026-10-06, after group 0
ran on Nitro: the PASS "lab host status" did not show that the lab host was
running. The operator saw `running` in `hl_lab.py status` at about 21:5x;
that, not the PASS, is the evidence.

## What was wrong

`check "lab host status" python3 tools/lab/hl_lab.py status` passes on exit
0, and `status` prints what it finds and exits 0 for every state.

## Fix

`status` prints one line for the domain's state, `hl-lab-host state:
<state>`, and group 0 passes only on `^hl-lab-host state: running$`.

## Test

`tests/acceptance_scripts_contract.py` takes the pattern from the group 0
script and applies it to `status` with a fake virsh reporting running, shut
off, paused and nothing: only running passes. It fails on the previous
script, which still checked the exit code.
