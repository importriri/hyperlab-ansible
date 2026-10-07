# Group 7's "cannot reach" checks passed on any error

Found in the review of the acceptance scripts on 2026-10-06, after group 7
ran on Nitro (`07-network-isolation-172348`, 9 PASS).

## What was wrong

"srv-tz-01 cannot reach the dev resolver" and "… the host's LLMNR" ran
`! timeout 3 bash -c '</dev/tcp/HOST/PORT'` in the guest and passed when
that failed. It also fails when `bash` or `timeout` is missing, when the
shell cannot run it at all, or when the guest has no network: nothing in
the PASS said the network had stopped the connection. Nor was there a
connection from the same guest that should succeed, so a guest that could
reach nothing would have passed both. Those two PASS do not count as
evidence; the loaded ruleset and its counters still do.

## Fix

`tools/acceptance/probes/tcp-probe` makes one connection attempt from the
guest and reports one word: reached, timeout, refused, unreachable,
cannot-run, or other with its exit code. Group 7 first requires the same
probe to reach srv-tz-01's own gateway DNS (allowed by the rules) as a
control. Only then does it judge the two refusals, and only timeout,
refused or unreachable pass. Without the control, the report says "NOT
JUDGED".

## Test

`tests/acceptance_scripts_contract.py` runs the probe against a listening
and a closed local port, without bash, and with timeouts that report a
drop, no route and an unknown error. It also runs group 7 in a
pseudo-terminal against fakes: a drop passes, a probe that cannot run
fails, and refusals without a control are not judged. It fails on the
previous script, which still negated a command.
