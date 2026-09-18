# Host Hyprland session lifecycle acceptance — 2026-09-18

## Scope

This milestone advances the physical host from the isolated Hyprland
first-launch proof to a managed login-session lifecycle while retaining Sway as
the recovery compositor. It builds on the [first controlled Host Hyprland launch acceptance](host-hyprland-first-launch-acceptance-2026-09-18.md).

Acceptance was performed on the Nitro validation host. Quickshell activation
and final login-screen visual theming are outside this milestone.

## Managed compositor lifecycle

HyperLab owns explicit user-session targets for both compositors:

- `hyperlab-hyprland-session.target`
- `hyperlab-sway-session.target`

Both integrate with `graphical-session.target`. HyperLab therefore owns the
compositor lifecycle edge instead of attempting to keep the passive graphical
target alive directly.

The managed Hyprland launcher uses `HYPRLAND_NO_SD_TARGET=1`; HyperLab owns the
target that controls its compositor-specific helper services and teardown.

The lifecycle wrapper publishes compositor environment to the user manager and
clears it during teardown. Sway publishes the IPC socket belonging to the exact
active Sway PID instead of accepting a stale socket from an older compositor.

## Ly session catalog

Ly exposes exactly two managed entries:

- `HyperLab Hyprland`
- `HyperLab Sway`

Native package session files remain installed. They are excluded from Ly's
selection catalog so a physical login cannot accidentally bypass the HyperLab
lifecycle wrapper.

The installed Ly policy disables the native Wayland, X11, xinitrc and shell
session sources while pointing `custom_sessions` at the private HyperLab
catalog.

The installed Ly 1.4.1 build is not treated as having a noninteractive
`--validate-config` gate: invoking that argument entered the TUI. Validation for
this milestone therefore comes from the exact installed policy plus the real
display-manager service successfully loading it and completing managed Sway
and Hyprland logins.

## Physical managed round-trip

The final real sequence was:

1. managed HyperLab Sway;
2. logout to Ly;
3. login through `HyperLab Hyprland`;
4. logout to Ly;
5. login through `HyperLab Sway`.

The managed Hyprland snapshot proved:

- exactly one Hyprland compositor;
- `HYPERLAB_SESSION_LIFECYCLE_MANAGED=1`;
- Hyprland XDG desktop and session identity;
- `graphical-session.target` active;
- `hyperlab-hyprland-session.target` active;
- `hyperlab-sway-session.target` inactive;
- HyperLab hypridle, hyprpaper, mako and polkit helpers active;
- the Hyprland portal backend active and the WLR portal backend inactive;
- no relevant failed user units.

The Hyprland logout snapshot proved:

- no compositor remained;
- both HyperLab compositor targets were inactive;
- compositor-specific helpers were inactive;
- compositor environment was cleared;
- no relevant failed user units remained.

The final managed Sway snapshot proved:

- exactly one Sway compositor;
- `HYPERLAB_SESSION_LIFECYCLE_MANAGED=1`;
- Sway XDG desktop and session identity;
- an IPC socket matching the active Sway PID;
- `graphical-session.target` active;
- `hyperlab-sway-session.target` active;
- `hyperlab-hyprland-session.target` inactive;
- Hyprland-specific HyperLab helpers inactive;
- the WLR portal backend active;
- no relevant failed user units.

The Hyprland portal service process was also still active in the final Sway
snapshot. A temporary acceptance watcher incorrectly treated backend process
liveness by itself as proof of backend selection and therefore reported the
final Sway stage as failed. The persistent repository lifecycle contract has no
such assertion. The managed Sway identity, exact IPC socket, target ownership,
WLR availability and failure state were all correct, so that temporary watcher
result was classified as a false negative.

## Ly UI observations

The Ly screen displayed `failed to get lock state` and, during one transition,
`failed to get user info`.

The account remained resolvable through NSS, PAM completed successful managed
logins, and both managed compositor sessions launched. These messages are
therefore recorded as non-blocking Ly UI observations rather than lifecycle
acceptance failures.

## Closeout runner note

An initial closeout invocation passed the lifecycle flag with Ansible
`key=value` extra-var syntax. Under the installed ansible-core strict
conditional behavior this produced a string rather than a boolean and was
correctly rejected before any repository publication.

The corrected closeout uses a JSON boolean extra var. This was a runner input
error, not a lifecycle source defect.

## Idempotence and verification

The managed lifecycle was applied on the real host. The closeout re-apply
completed at `changed=0`.

The full repository verification suite was executed after the acceptance
documentation was added and before publication.

## Result

**PASS**

The managed Host Hyprland session lifecycle is accepted on Nitro.

Sway remains installed and available as the recovery compositor.
