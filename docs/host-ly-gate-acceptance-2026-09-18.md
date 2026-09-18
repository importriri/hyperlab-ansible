# HyperLab Gate acceptance — Nitro — 2026-09-18

## Scope

This milestone closes the final Ly presentation gate for the managed physical
host sessions.

The security and session-lifecycle model is unchanged. The Gate is a
presentation-only layer over the already accepted managed Ly catalog and
session wrappers documented in
[`host-hyprland-session-lifecycle-acceptance-2026-09-18.md`](host-hyprland-session-lifecycle-acceptance-2026-09-18.md).

## Accepted presentation

The physical Nitro host accepted the following login surface:

- dedicated `HyperLab Gate` identity;
- near-black background;
- crimson/red Matrix animation rather than the Ly green default;
- brighter crimson Matrix heads;
- cool neutral foreground text;
- managed Ly session choices remain `HyperLab Hyprland` and `HyperLab Sway`;
- no coupling between the Gate and the runtime Green, Violet, Blue or Red
  desktop palette.

The Gate deliberately avoids decorative security claims, fake authentication
messages and theme-dependent trust semantics.

## Matrix timing

The first physical presentation used an animation frame delay of 38 ms.

Operator feedback accepted the composition but requested approximately 1.5
times faster Matrix motion. The managed delay was changed to 25 ms, a 1.52x
speed increase relative to the first value.

The 25 ms value was applied on the physical Nitro host and reached through the
subsequent logout/login validation path.

## Automation acceptance

The focused Gate contract and the existing M11 visual contract passed.

The host desktop role was then executed twice against the real Nitro host.
The first run applied the presentation changes. The second run completed with:

`changed=0 unreachable=0 failed=0`

The installed `/etc/ly/config.ini` contained the managed Gate values including
`animation = matrix`, the crimson CMatrix colours and
`animation_frame_delay = 25`.

## Validation-harness Firefox incident

During the temporary physical acceptance harness, Ly was deliberately restarted
by a privileged watcher after the compositor disappeared so the new theme could
be inspected without rebooting the machine.

After one return to managed Sway, Firefox reported that another Firefox instance
was still running. A reboot cleared the symptom.

Follow-up read-only classification found that the current Firefox process and
Sway both belong to the same login-session cgroup. The persistent HyperLab
logout path exits the compositor and clears managed session state, while the
product code does not restart Ly during normal logout.

The incident is therefore classified as consistent with a temporary
acceptance-watcher timing race. A persistent HyperLab lifecycle regression was
not demonstrated, so no process-kill workaround or broader session teardown was
added to production policy.

## Result

HyperLab Gate is accepted on the Nitro validation host.

The login visual identity is now independent from desktop theme selection,
idempotent under the managed role and layered on top of the previously accepted
managed Sway/Hyprland lifecycle.

Quickshell remains separate later presentation work.
