# Problem index

These notes keep the failures that changed a HyperLab contract. Start from the
symptom; each page records what was actually wrong, the fix and the regression
proof.

- [`ansible-group-vars-outside-repo.md`](ansible-group-vars-outside-repo.md): a
  test playbook in `/tmp` lost repository `group_vars`.
- [`hyprland-nvidia-headless-output.md`](hyprland-nvidia-headless-output.md):
  NVIDIA-only Hyprland started with no output.
- [`ly-login-environment.md`](ly-login-environment.md): compositor variables
  were configured but missing from the running session.
- [`looking-glass-linux-gcc16.md`](looking-glass-linux-gcc16.md): the pinned
  Linux sender failed to build with GCC 16.
- [`looking-glass-linux-pipewire-frame-lifetime.md`](looking-glass-linux-pipewire-frame-lifetime.md):
  PipeWire frame lifetime and thread-loop locking caused a sender crash.
- [`looking-glass-linux-pipewire-disconnect-lifetime.md`](looking-glass-linux-pipewire-disconnect-lifetime.md):
  PipeWire stream teardown during a real client disconnect could crash the Linux sender.
- [`looking-glass-linux-sdr-flagged-hdr.md`](looking-glass-linux-sdr-flagged-hdr.md):
  the pinned PipeWire sender marked every SDR frame HDR PQ, so colour-managed
  clients tagged sRGB surfaces as ST2084.
- [`guest-idle-lock-blanked-looking-glass.md`](guest-idle-lock-blanked-looking-glass.md):
  a guest reached through Looking Glass no longer locks itself when idle.
- [`focus-accent-kept-old-resolver.md`](focus-accent-kept-old-resolver.md):
  the border and keyboard service now follows a resolver pulled into the
  checkout.
- [`guest-theme-replaced-identity-wallpaper.md`](guest-theme-replaced-identity-wallpaper.md):
  a guest theme changes colours only; the identity wallpaper stays.
- [`guest-foreign-identity-themes.md`](guest-foreign-identity-themes.md):
  a guest now carries and offers only its own identity theme.
- [`guest-launcher-opened-rofi.md`](guest-launcher-opened-rofi.md): rofi
  stands in only for a guest shell that is not running.
- [`surface-provenance-missed-projected-machines.md`](surface-provenance-missed-projected-machines.md):
  the host bar could not resolve a Machine's window because the resolver
  ignored projected specs.
- [`guest-clock-in-utc.md`](guest-clock-in-utc.md): guests ran in UTC; every
  new Machine now follows the hypervisor's time zone from its first boot.
- [`guest-wallpaper-key-redrew-session.md`](guest-wallpaper-key-redrew-session.md):
  `ALT+SHIFT+W` reloaded the whole session and ran a 1.1 s transition; it
  now changes only the wallpaper with a short fade.
- [`guest-kvmfr-owner-before-account.md`](guest-kvmfr-owner-before-account.md):
  on a new Machine udev resolved the kvmfr owner before cloud-init created
  the account; the role re-reads the rules when that happened.
- [`guest-host-key-unknown-after-first-boot.md`](guest-host-key-unknown-after-first-boot.md):
  a new Machine's SSH host key is now read through QEMU Guest Agent and
  pinned, never accepted from the network.
- [`vfio-registry-refused-second-definition.md`](vfio-registry-refused-second-definition.md):
  a second VFIO Machine was refused while the first was shut off; the GPU
  is now owned only by the running domain.
- [`image-factory-block-condition-skipped-lock-release.md`](image-factory-block-condition-skipped-lock-release.md):
  a successful import skipped its own final check and kept its lock, because
  the commit changed the block's condition.
- [`workbench-root-dotfiles-in-image.md`](workbench-root-dotfiles-in-image.md):
  root's configuration, cache and npm directories reached the first captured
  image; the seal deletes them and the scan refuses them.
- [`workbench-machine-id-after-run-command.md`](workbench-machine-id-after-run-command.md):
  the sealed image kept a machine-id written after the generalization; the
  seal now empties it last.
- [`workbench-sysprep-user-account-arch.md`](workbench-sysprep-user-account-arch.md):
  `virt-sysprep`'s user-account operation cannot read Arch's `login.defs`; the
  Workbench removes users with the guest's own `userdel`.
- [`workbench-sysprep-format-order.md`](workbench-sysprep-format-order.md): the
  first Workbench seal failed because `--format` followed `-a`, and the error
  was hidden behind the tool's bug-report advice.
- [`guest-new-window-opened-maximized.md`](guest-new-window-opened-maximized.md):
  a second terminal hid the first because it opened maximized at the
  application's request.
- [`guest-lua-gradient-border.md`](guest-lua-gradient-border.md): Hyprland's
  Lua configuration refused the classic gradient border string.
- [`guest-hyprctl-dispatch-takes-lua.md`](guest-hyprctl-dispatch-takes-lua.md):
  Desk keys did nothing because `hyprctl dispatch` takes a Lua expression under
  Hyprland's Lua configuration.
- [`guest-stale-package-database.md`](guest-stale-package-database.md): new
  guest packages were requested against a stale sync database and the mirrors
  answered 404; the install is now one full system transaction.
- [`guest-shell-stale-place-at-signal.md`](guest-shell-stale-place-at-signal.md):
  the Desk OSD read a binding before Qt re-evaluated it and announced the
  project of the Desk being left.
- [`guest-theme-change-second-bar.md`](guest-theme-change-second-bar.md): the
  guest theme controller always restarted Waybar, which would have drawn a
  second bar beside the Workspace Shell.
- [`guest-shell-offscreen-harness.md`](guest-shell-offscreen-harness.md): the
  offscreen harness found a shadowed `palette`, a binding loop and a refused
  anchor in the guest shell before any guest ran it.
- [`guest-waybar-over-fullscreen.md`](guest-waybar-over-fullscreen.md):
  the guest shortcut requested maximization instead of true fullscreen; the
  native fullscreen correction is software-verified, deployed and physically
  accepted on Nitro, including Waybar hide and restore.
- [`looking-glass-guest-tearing.md`](looking-glass-guest-tearing.md):
  the reported Valley flicker was physically localized upstream into Valley's
  application-specific OpenGL/GLX/Xwayland path; direct guest and X11 captures
  contain it while Heaven is clean. It is not a HyperLab/Looking Glass
  presentation blocker.
- [`kvmfr-guest-device-sizing.md`](kvmfr-guest-device-sizing.md): host module
  sizing was incorrectly treated as guest policy.
- [`libvirt-kvmfr-cgroup-acl.md`](libvirt-kvmfr-cgroup-acl.md): QEMU could see
  kvmfr on the host but its device ACL still blocked the open.
- [`drawer-layer-shell-margins.md`](drawer-layer-shell-margins.md): correct
  Layer Shell anchors were undermined by stale top/left margins.
- [`nitro-an515-55-rgb-protocol.md`](nitro-an515-55-rgb-protocol.md): sysfs
  accepted RGB writes while the physical AN515-55 keyboard turned off.
- [`nitro-sense-dkms-transaction.md`](nitro-sense-dkms-transaction.md): a
  managed driver update cleaned recovery state before the new runtime was
  proved.
- [`nitro-sense-kbuild-recursion.md`](nitro-sense-kbuild-recursion.md): a
  temporary Kbuild wrapper was reused as input and recursively called itself.
- [`nitro-sense-patch-truncation.md`](nitro-sense-patch-truncation.md): direct
  shell redirection truncated the reviewed overlay after an earlier step failed.
- [`nitro-sense-fan-policy.md`](nitro-sense-fan-policy.md): a healthy service
  applied `0,0` because the requested policy itself still meant firmware auto.
- [`nitro-sense-dkms-provenance.md`](nitro-sense-dkms-provenance.md): the
  target DKMS state was already present when the expected real transition was
  observed; provenance remains open.
- [`nitro-suspend-resume-evidence-race.md`](nitro-suspend-resume-evidence-race.md):
  a post-resume snapshot was captured before the kernel had completed suspend.
- [`nitro-wmi-unknown-function-four.md`](nitro-wmi-unknown-function-four.md):
  the accepted AN515-55 campaign keeps an unclassified WMI event visible.
- [`ansible-become-password-handoff.md`](ansible-become-password-handoff.md):
  a chained hardware gate needed one validated credential and a stable private
  handoff to each Ansible process.
- [`guest-package-upgrade-recovery.md`](guest-package-upgrade-recovery.md): an
  interrupted Arch upgrade required restoring the complete package/kernel
  transaction before guest acceptance continued.
- [`host-desktop-looking-glass-order.md`](host-desktop-looking-glass-order.md):
  a clean rebuild proved that host desktop/session state must land before
  Looking Glass integration.
- [`looking-glass-input-isolation.md`](looking-glass-input-isolation.md): real
  Linux guest video is proved, while host/guest input isolation remains a
  separate open acceptance gate.

- [`looking-glass-render-jinja-assertion.md`](looking-glass-render-jinja-assertion.md):
  the render suite still fails on a Jinja-in-a-constant-string provenance
  assertion; the verifier gate remains open.
- [`control-center-single-surface-dismissal.md`](control-center-single-surface-dismissal.md):
  click-outside dismissal moved from competing Layer Shell/focus paths to one
  cockpit-owned `Gtk.Overlay`.
- [`runtime-inventory-self-heal.md`](runtime-inventory-self-heal.md): ephemeral
  guest inventory recovery must stay behind the authoritative CLI and strict
  runtime-file validation; its final integration gate is still open.
- [`waybar-render-contract-drift.md`](waybar-render-contract-drift.md): shell
  tests now protect mounted modules and routes semantically instead of dead
  hidden modules or positional render indexes.
- [`ly-package-config-validation.md`](ly-package-config-validation.md): the
  installed Ly rejected an assumed validation option, so the role now preserves
  the package configuration and verifies only targeted edits.

- [`trust-palette-theme-drift.md`](trust-palette-theme-drift.md): theme
  variants changed security-domain colors while the Control Center treated
  those colors as immutable semantics.
- [`nitro-sense-led-capability-split.md`](nitro-sense-led-capability-split.md):
  one four-zone allowlist authorized both static colors and a distinct,
  unproved firmware-effect path.

- [`palette-terminal-trust-coupling.md`](palette-terminal-trust-coupling.md):
  Foot ANSI slots borrowed trust-domain tokens, so making trust semantic also
  changed ordinary terminal appearance.

- [`nitro-control-backend-check-mode-preview.md`](nitro-control-backend-check-mode-preview.md):
  the out-of-tree safety stop originally hid the runtime backend landing from
  check mode; the preview now renders files without starting services.

- [`nitro-control-backend-runtime-validation.md`](nitro-control-backend-runtime-validation.md):
  physical end-to-end proof for the typed Nitro runtime privilege boundary.
- [`nitro-keyboard-idle-timeout.md`](nitro-keyboard-idle-timeout.md):
  AN515-55 lighting can idle off and wake on keypress without an exposed timeout ABI.

- [`control-center-trust-color-contract.md`](control-center-trust-color-contract.md):
  geometry verifier followed stale manager literals after trust colors moved to shared palettes.

- [`control-center-theme-reentrant-reload.md`](control-center-theme-reentrant-reload.md):
  synchronous theme selection re-entered the resident GApplication and timed out.

- [`control-center-theme-sway-reload-dismissal.md`](control-center-theme-sway-reload-dismissal.md):
  Sway reload replaced the resident manager while an internal theme selection was still visible.

- [`nitro-control-backend-extra-fields.md`](nitro-control-backend-extra-fields.md):
  the privileged JSON protocol originally ignored fields outside the reviewed operation schema.

- [`documentation-navigation-orphans.md`](documentation-navigation-orphans.md):
  four top-level operator and architecture contracts were added without inbound documentation links.
- [`looking-glass-render-nested-jinja-contract.md`](looking-glass-render-nested-jinja-contract.md):
  a render invariant embedded a role template inside another Jinja expression and searched for the expanded value.

- [`looking-glass-launcher-path-ownership.md`](looking-glass-launcher-path-ownership.md):
  the Control Center action chain reached the correct opener, but the final client executable was still selected through session PATH.
- [`vfio-reboot-power-cycle-recovery.md`](vfio-reboot-power-cycle-recovery.md):
  a guest-only reboot left the Nitro RTX 3060 path unhealthy while an explicit full-QEMU Power cycle restored QGA, networking, NVIDIA and Looking Glass readiness.

- [`sbctl-export-enrolled-keys-landlock.md`](sbctl-export-enrolled-keys-landlock.md):
  the read-only firmware-key export hit the upstream Landlock/output-directory
  bug and now uses a narrow sandbox exception.
- [`operator-shell-strict-mode-leak.md`](operator-shell-strict-mode-leak.md):
  an interactive paste block leaked strict shell options and exited the
  operator terminal on a later non-zero command.
- [`secure-boot-enrollment-handoff.md`](secure-boot-enrollment-handoff.md):
  signed boot artifacts were prepared while the real firmware enrollment and
  runtime Secure Boot proof remained a hardware gate.
- [`dkms-module-signing-trust.md`](dkms-module-signing-trust.md):
  signed out-of-tree modules still lack a proved kernel trust path for a future
  stricter lockdown/module-enforcement policy.
- [`guest-hyprland-autologin-regex-validation.md`](guest-hyprland-autologin-regex-validation.md):
  the guest Ly autologin guard rejected the valid absolute path
  `/usr/bin/Hyprland` because of its regular expression.
- [`linuwu-sense-linux-7.2-strncpy-removal.md`](linuwu-sense-linux-7.2-strncpy-removal.md):
  the pinned Nitro platform driver stopped building on Linux 7.2 at its
  remaining `strncpy()` calls; reboot stayed blocked until a module for the new
  kernel was proved.
- [`nitro-sense-settings-after-driver-reload.md`](nitro-sense-settings-after-driver-reload.md):
  a managed driver reload left the persistent Nitro settings unapplied, and the
  role fell into its full rollback path.
- [`looking-glass-linux-prelogin-primary-handoff.md`](looking-glass-linux-prelogin-primary-handoff.md):
  Looking Glass's built-in SPICE fallback was unreliable for login input; login
  now goes through an owned console before handing over to Looking Glass.
- [`managed-machine-provenance-claim.md`](managed-machine-provenance-claim.md):
  a self-asserted `managed-machine` tag let a dirty plan write a clean
  root-owned GPU handoff policy.
- [`product-inventory-hid-fixture-domains.md`](product-inventory-hid-fixture-domains.md):
  product-only Machines hid running fixture domains while the empty state
  promised they were in Diagnostics.
- [`c10-contract-fixtures-behind-runtime.md`](c10-contract-fixtures-behind-runtime.md):
  the focused C10 gate passed while three discovered contracts still encoded
  pre-C10 fixtures.

Author: [importriri](https://github.com/importriri).
