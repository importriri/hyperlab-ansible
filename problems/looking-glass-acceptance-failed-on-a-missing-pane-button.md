# Group 16 failed and stopped when the pane had no Restart capture

Seen on Nitro, 2026-10-12, in group 16 (`16-looking-glass-sender-224919`):
9 PASS, then FAIL at "Restart capture used once from the pane" and at "the
pane's restart left a new sender with its own start line". The operator
reported that dev-01's Machine pane offered Console, SSH, Looking Glass,
Shut down, Reboot guest and Force stop, and no Restart capture.

## What happened

- The pane's Restart capture came with ADR 0045 (commit 7257327,
  2026-10-05). On Nitro the installed shell is older:
  `/etc/xdg/quickshell/hyperlab` dates from 2026-10-04 and
  `/usr/local/bin/privatestack-machine-actions` from 2026-09-27, and
  neither contains `restart-capture`. The host desktop playbook has not run
  since.
- The script asked the operator to confirm the restart, then whether it was
  used, with no way to say that the button was not there. The answer "no"
  became a FAIL of the sender step, and the group stopped.

## Fix

Before the restart the script asks whether dev-01's pane offers Restart
capture. Only `n` is reported as `N/A` with its reason: neither PASS nor
FAIL, and the group ends without stopping; the summary counts it apart
("1 not available"). Any other answer, or none, is a FAIL and stops the
group, so a typo cannot skip the step. `offered` in
`tools/acceptance/lib.sh` does this for any group.

## Regression proof

`tests/acceptance_scripts_contract.py` runs group 16 against fake tools
with the operator answering that the pane has no Restart capture: the
report has the `N/A` line, no FAIL, no STOPPED, and ends "0 failed, 0
skipped, 1 not available". Against the previous script: `16 does not say
the pane has no Restart capture` (it asked for the restart and stopped).
With the N/A branch not letting the group end: `a pane without Restart
capture failed or stopped 16`.
An empty answer is a FAIL that stops the group; with every answer but `y`
taken as N/A (the first version of this fix, found in review): `an answer
other than n was taken as a pane without Restart capture`.

Reviewed and left as it is (2026-10-13): a group with an N/A still exits
0, as with a skipped step; the summary line and the report say it, and
nothing reads the exit status alone.

## Still open

The pane's Restart capture is untested on Nitro until the host desktop
playbook installs the current shell: ADR 0045's hardware test, items 2 to 5.
