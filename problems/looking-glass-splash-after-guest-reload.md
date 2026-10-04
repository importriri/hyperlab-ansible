# Looking Glass stayed on its splash screen after `hyprctl reload` in the guest

Author: [importriri](https://github.com/importriri).

Status: diagnosis open, waiting for a reproduction on Nitro. The sender now
keeps the evidence that was missing; no behaviour was changed blindly.

## Symptom

On 2026-10-04 four `hyprctl reload` runs inside `dev-01` (09:10–09:12, while
measuring `ALT+SHIFT+W`) were followed by a Looking Glass client that showed
only its splash screen. Restarting the whole Machine recovered it.

## What was observed

Read on `dev-01` without privilege, in the user journal of that boot:

- each reload is followed by `hyprpolkitagent: wayland output 72: done`
  (09:10:55, 09:11:22, 09:11:46, 09:11:48): the compositor announces its
  output again to every client, so a configuration reload reaches the
  `HEADLESS-0` output the sender captures;
- the sender is not a unit: `hyperlabctl open looking-glass` starts
  `/usr/local/bin/looking-glass-host` under a small supervisor over SSH, and
  the supervisor only stops it when Hyprland disappears; a sender that stays
  alive but stops producing frames is never restarted;
- the sender's log of that boot was gone: every launch wrote
  `~/.local/state/hyperlab/looking-glass-host.log` from scratch, and the next
  boot's launch replaced it.

## Not yet proven

That the reload broke the sender's capture (rather than, for example, the
client or the kvmfr device) is likely but not shown: there is no sender log
from the failure. A fix that restarts the sender on every output change, or
that blocks reloads, would be a guess.

## Change made now

The supervisor keeps the previous run's log as `looking-glass-host.log.1`,
starts each log with the time and the Hyprland instance it was started for,
and ends it with how the sender stopped (its exit status, or Hyprland gone).

## Next step

The reproduction in the test plan collects the sender log, the user journal
and `hyprctl monitors` before and after one reload, then recovers without a
VM restart by stopping the sender and opening Looking Glass again. The fix
follows the evidence.

## Regression proof

`tests/looking_glass_sender_log_contract.py` runs the real supervisor with a
fake sender and a fake `pgrep`: the previous log must survive as `.1`, and
the new log must name the start time and Hyprland instance and record the
sender's exit status or the loss of Hyprland.
