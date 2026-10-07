# Group 16 passed checks against a sender it had not rebuilt

Seen on Nitro, 2026-10-06, in group 16 (`16-looking-glass-sender-220141`).
The run is not verified: every "(operator)" PASS was annulled, and the
operator's screenshots at 22:12 show the Looking Glass client on its
waiting logo.

## What happened

- The script applied the whole workstation profile
  (`guest-arch-dev-vfio.yml`) to dev-01 without a confirmation. Its full
  package synchronization upgraded `linux-zen` 7.2.8 to 7.2.9 under the
  running kernel, and `guest_gpu_nvidia` then refused, "The running Zen
  kernel needs its matching build tree". The play stopped before
  `guest_looking_glass_linux`: the sender with the A5 fix was never built.
- The script went on. "health is ok" passed on the exit code of a command
  that exits 0 for every answer (the word was `idle`). "no stall on a still
  desktop" passed on the absence of a line in a log that had not been
  written for 4.6 hours, by a sender that cannot write that line. The
  operator was asked three questions in front of the waiting logo.

## Fix

- Only the sender's own playbook, `guest-looking-glass-linux.yml`, which
  upgrades nothing and now refuses a running kernel without its build tree.
  It stops at a confirmation that says so, and a second confirmation before
  the sender is restarted ("the stream stops for a few seconds").
- The role writes the built binary's sha256 into the sender's stamp.
  `tools/acceptance/sender_identity.py` passes the running sender only when
  its stamp's commit and patch digests are the repository's, the running
  executable (`/proc/PID/exe`) is the stamped binary, it is a new process
  (or the same one, when that is the point), and its log begins with its own
  start line after the step began. A stamp without the binary digest is
  "rebuild needed".
- Health passes only on the word `ok`. "Restart capture" from the pane must
  leave a new sender with its own start line.
- Fail closed: a failed or skipped step ends the group before any question
  to the operator.
- The same confirmation rule found group 10 starting `srv-tz-01` with
  `vm-start.yml` unasked; it now stops at a confirmation too.

## Test

`tests/acceptance_scripts_contract.py`:

- judges good and bad probes with `sender_identity.py`;
- requires every playbook applied to a Machine to sit behind a
  confirmation, and no whole workstation profile in any acceptance script;
- requires health to be judged on its word;
- runs group 16 for real in a pseudo-terminal against fakes: a failed
  playbook, and a sender that is not this build, both stop it before any
  question.

`tests/looking_glass_linux_contract.py` holds the binary digest and the
kernel refusal. Run against dev-01, read-only, the identity check reports
the sender that ran on 2026-10-06 as an old runtime patch with no binary
digest. The contract fails on the previous scripts.
