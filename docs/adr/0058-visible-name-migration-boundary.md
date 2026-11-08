# ADR 0058 - Record the remaining visible name migration

Status: Proposed.

## Context

QML-owned shell labels and CLI help/version read the shared product identity.
Other visible surfaces still display the previous name, including reasons
supplied to the native Machines pane by its bridge. They are visible product
surfaces, not internal identifiers. Their migration needs their deployment
and runtime readers to consume the shared identity as well.

The product documentation contract forbade every old product word except the
history sentence. That also rejected an accurate description of the session
labels actually installed in Ly. Replacing those labels with generic prose
hid an unfinished migration and made the README less useful at login.

## Decision

Proposed: retain the existing surfaces inventoried below for now and list
each one in an open release-roadmap item. Keep the physical presentation
gate open. The software checkbox covers QML-owned labels/titles, CLI
help/version and application names in the three host theme, keyboard and
fallback-bar notification helpers. It excludes bridge-provided reasons,
operation terminals, lock and login labels, helper diagnostics, vault dialogs,
guest notifications and CLI runtime diagnostics; the visible migration remains
incomplete.

Read the CLI identity only while formatting help or executing `--version`.
Invalid display input refuses those presentations with exit 2 and no fallback
name. It must not block command dispatch, including `panic engage`, `panic
status` or `panic restore`: emergency stop cannot depend on a cosmetic file.
The bounded ASCII identity grammar remains unchanged. A proposed spelling
outside it refuses help/version, shell identity, focus and host notifications
until the readers are updated together; it does not disable CLI operations.
Product identity is display input, not a policy authority.

Keep the same byte grammar and path refusals in every reader. Python preserves
line endings with `newline=""`; Bash uses a function-local `LC_ALL=C` so ranges
do not widen under a language locale. The shell replaces its unguarded
FileView identity read with the existing compositor adapter's fixed,
read-only `product-identity` route. That route accepts no arguments or paths,
needs no active compositor, and reuses the focus reader's leaf/parent,
regular-file and readable-mode checks. Its internal `--document` mode returns
the exact validated bytes, including their original line ending. Every Bash
reader retains the same function body; notification/focus callers keep the
name-only result. Explicit mode bits are intended to refuse zero-mode files
even when the execution identity could otherwise read them; that behavior is
not verified here. Normal-user fixtures cannot distinguish this guard from
the kernel's permission refusal. QML retains its grammar and publishes identity
only after a successful normal bridge exit. Failed startup or reading leaves
identity empty. This adds one short-lived bridge process at shell startup and
no deployment path. QML
still cannot start an interpreter or bypass the existing provenance bridge.
No reader supplies a default name. The shared fixture table checks LF, CRLF,
no newline, lone CR, accented words, malformed/duplicate fields, extra lines,
NUL bytes, long fields and missing, unreadable, nonregular or redirected paths.
Bash runs the table under C and every installed UTF-8 locale. The contract
requires at least one non-C UTF-8 locale whose unguarded Bash ranges accept
an accented word; C/C.utf8 alone refuses verification rather than hiding
an unexercised widening case.

Correct the documentation check with one exact README sentence naming the
installed Ly sessions. Parse the desktop entries to pin those names, and
parse the Waybar brand/tooltip to keep the deferred inventory explicit.
All other old product prose remains rejected except the history sentence.
This exception documents existing behavior; it does not permit additional
old-name strings or change command names, paths or session identifiers.

## Deferred surface inventory

These are known remaining surfaces at `db7c99b`, including the additional
host login, guest desktop/session and helper labels identified below. This is
a baseline inventory, not an exhaustive claim about every visible string in
the tree. The contract
requires each known file in the open roadmap item; later discoveries must be
added to both records before the physical presentation gate can close.

- `hyperlab-hyprland.desktop` and `hyperlab-sway.desktop`: Ly session names
  and comments under `roles/host_desktop_hyprland/files/`.
- `hyperlab-control-center.desktop`: application name and keywords under
  `roles/host_desktop_sway/files/`.
- `privatestack-hyperlab-domains.py`: retained GTK Control Center title.
- `waybar.jsonc`: fallback brand and compact drawer tooltip.
- `privatestack-swaybar-status.py`: native recovery-bar brand.
- `privatestack-theme.sh`: product-wallpaper mode tooltips.
- `privatestack-controls.sh`: rofi title, entries and matching dispatch.
  These five files are under `roles/host_desktop_sway/files/`.
- `privatestack-machine-actions.py`: bridge refusal reasons under
  `roles/host_desktop_common/files/`, displayed by the native Machines pane:
  `invalid HyperLab spec inventory`,
  `machine maps to more than one HyperLab spec`,
  `managed action has no HyperLab spec`,
  `this managed machine's HyperLab spec is unavailable`,
  `machine metadata and HyperLab spec disagree`, and `invalid HyperLab checkout`.
  The command-line refusal prefix also retains the previous name.
- `privatestack-operation.py`: terminal title, reviewed-operation transcript
  header and completion text under `roles/host_desktop_common/files/`.
- `hyperlab-vault-confirm.py`: vault confirmation dialog title under
  `roles/host_vault/files/`.
- `hyperlab-clipboard-receive.py`: guest clipboard notification application
  name and refusal prefix under `roles/guest_desktop_hyprland/files/`.
- `hardware.py`: runtime reasons from `hyperlabctl doctor --hardware` under
  `tools/hyperlabctl/hyperlabctl/`, including UEFI, IOMMU, GPU, memory and
  Secure Boot diagnostics.
- `hyprlock.conf.j2`: the host lock wordmark `HyperLab` and subtitle `Platform`
  under `roles/host_desktop_hyprland/templates/`. Its deployment and label
  reader remain deferred with the other lock/login surfaces.
- `privatestack-shell-actions.py`: stderr carried through ShellActions into
  Diagnostics operation details under `roles/host_desktop_common/files/`.
  ShellSurfaces also retains it in failure-OSD state; the OSD displays
  `Failed` rather than the full reason:
  `HyperLab: rejected arguments for fixed action:`,
  `HyperLab: rejected unknown shell action:`,
  `HyperLab: rejected invalid argument for action:`,
  `HyperLab: rejected an application outside the reviewed catalogue or not installed:`,
  and `HyperLab: rejected unavailable or untrusted target:`.
- `privatestack-machine-provision.py`: provisioning refused, cancelled and
  stopped stderr under `roles/host_desktop_common/files/`.
- `hyperlab-gaming-mode.py`: the Gaming Mode `--help` description under
  `roles/host_gaming_mode/files/`.
- `privatestack-hyperlab-session.sh`: the manager-did-not-stop refusal under
  `roles/host_desktop_sway/files/`.
- `hyperlab-desk.py`: the guest lock-label fallback `HyperLab Workstation`
  and the desk-qualified lock label under `roles/guest_desktop_hyprland/files/`.
- `roles/guest_desktop_hyprland/tasks/main.yml`: the guest Ly
  `initial_info_text` value `HyperLab guest workstation`.
- `roles/host_desktop_sway/defaults/main.yml`: host Ly `box_title`
  `HyperLab Gate` and `initial_info_text` `HyperLab host gateway`, deployed
  by `roles/host_desktop_sway/tasks/main.yml` into the host login screen.
- `DesktopLayer.qml` under
  `roles/guest_desktop_hyprland/files/quickshell/hyperlab-workspace/`: guest
  idle-desktop fallback `HYPERLAB WORKSTATION` when no desk is named.
- `hyperlab-hyprland.desktop.j2` under
  `roles/guest_desktop_hyprland/templates/`: guest Ly session name
  `HyperLab Hyprland` and comment
  `Deterministic Hyprland session for the HyperLab VFIO guest`.
- `privatestack-keyboard.sh` under `roles/host_desktop_sway/files/`: stderr
  format `HyperLab: compositor rejected keyboard layout %s (index %s, order %s).`.
- `hyperlab-gaming-mode-root.py` under `roles/host_gaming_mode/files/`:
  argparse description `Root guard for HyperLab Gaming Mode`.
- `ly-guest-login.sh.j2` under `roles/guest_desktop_hyprland/templates/`:
  stderr format `HyperLab: NVIDIA DRM device did not become ready: %s`.

## Evidence and consequences

The product contract requires the exact session-label sentence, every file
in this inventory in the open roadmap item, and these bridge refusal literals
through an AST scan. The same scan checks shell-action stderr prefixes;
parsed host hyprlock label blocks, the guest lock-label function and guest
Ly task data pin the known lock/login strings. Parsed host Ly defaults pin
both host gate labels. Every repository desktop source, including the guest
template, must be inventoried with its parsed Name and Comment. The QML scan
covers the host shell and guest workspace recursively, allowing exactly one
instance of the pinned guest desktop fallback in its existing file. Shell
printf tokens and the root Gaming Mode parser AST pin the additional helper
messages above. Removing an entry or adding another old-name QML string fails.
New help literals naming the old product also fail through an AST check; the two
existing literals rewritten by the CLI formatter are enumerated explicitly.
QML presentation fixtures reject old
names in evaluated text and accessibility attributes; their inert bridge data
does not verify the deferred live refusal messages. Isolated entry-point
fixtures require `panic status` to work with invalid identity while help and
version still refuse it normally.

A later visible migration must update deployment, runtime consumers, the
inventory and these narrow checks together. No Nitro or Predator visual
acceptance follows from these software results.
