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
operation terminals, vault dialogs, guest notifications and CLI runtime
diagnostics; the visible migration remains incomplete.

Read the CLI identity only while formatting help or executing `--version`.
Invalid display input refuses those presentations with exit 2 and no fallback
name. It must not block command dispatch, including `panic engage`, `panic
status` or `panic restore`: emergency stop cannot depend on a cosmetic file.
The bounded ASCII identity grammar remains unchanged. A proposed spelling
outside it refuses help/version, shell identity, focus and host notifications
until the readers are updated together; it does not disable CLI operations.
Product identity is display input, not a policy authority.

Correct the documentation check with one exact README sentence naming the
installed Ly sessions. Parse the desktop entries to pin those names, and
parse the Waybar brand/tooltip to keep the deferred inventory explicit.
All other old product prose remains rejected except the history sentence.
This exception documents existing behavior; it does not permit additional
old-name strings or change command names, paths or session identifiers.

## Deferred surface inventory

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

## Evidence and consequences

The product contract requires the exact session-label sentence, every file
in this inventory in the open roadmap item, and these bridge refusal literals
through an AST scan. Removing an entry fails. New help literals naming the old product
also fail through an AST check; the two existing literals rewritten by the
CLI formatter are enumerated explicitly. QML presentation fixtures reject old
names in evaluated text and accessibility attributes; their inert bridge data
does not verify the deferred live refusal messages. Isolated entry-point
fixtures require `panic status` to work with invalid identity while help and
version still refuse it normally.

A later visible migration must update deployment, runtime consumers, the
inventory and these narrow checks together. No Nitro or Predator visual
acceptance follows from these software results.
