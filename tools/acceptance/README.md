# Nitro acceptance scripts

One script per group of the operator's test plan that needs the real
hardware. Each one runs the group's checks, keeps the evidence under
`~/hyperlab-evidence/<date>/<group>-<time>/` (report, logs, backups,
screenshots) and prints PASS or FAIL per check. It asks for the sudo
password at most once; a destructive step stops and runs only if the
operator types the word it shows. A step previewed by a check mode is
offered only after that check mode passed. `tests/acceptance_scripts_contract.py`
holds them to these rules; `lib.sh` has the helpers.

| Order | Script | About | Approves |
|---|---|---|---|
| 1 | `07-network-isolation.sh` | 15 min | the fail-closed guest isolation and the lab network's rules |
| 2 | `00-lab-host.sh` | 5 min | starting the nested lab host (ADR 0046) |
| 3 | `11-usbguard.sh` | 10 min | the host USB policy (ADR 0038) |
| 4 | `10-apparmor-boot.sh prepare`, then after the reboot `verify` | 20 min | the AppArmor boot entry (ADR 0037) |
| 5 | `12-fullscreen-ring.sh` | 5 min | the fullscreen ring (ADR 0039) over Looking Glass and over a SPICE console, none over a host window; waits up to 60 s for dev-01's health `ok` and asks nothing before |
| 6 | `16-looking-glass-sender.sh` | 30 min | the sender fix, stream health and the SUPER key (A5, ADR 0045); rebuilds only the sender, after a confirmation, and stops before any question when a step fails; waits up to 60 s for the health `ok` before asking whether the desktop shows, and names a missing client; a pane without Restart capture is reported N/A, not FAIL; a 5-minute still phase timed by the script and a 30 s changing phase (temporary notifications in dev-01 that close by themselves), judged from the sender's log by `sender_phases.py` |

Run from the repository root, in the graphical session (screenshots use
`grim`): `tools/acceptance/07-network-isolation.sh`.
