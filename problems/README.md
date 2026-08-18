# Problem index

These notes keep the failures that changed a HyperLab contract. Start from the
symptom; each page records what was actually wrong, the fix and the regression
proof.

- [`ansible-group-vars-outside-repo.md`](ansible-group-vars-outside-repo.md): a
  test playbook in `/tmp` lost repository `group_vars`.
- [`hyprland-nvidia-headless-output.md`](hyprland-nvidia-headless-output.md) -
  NVIDIA-only Hyprland started with no output.
- [`ly-login-environment.md`](ly-login-environment.md): compositor variables
  were configured but missing from the running session.
- [`looking-glass-linux-gcc16.md`](looking-glass-linux-gcc16.md): the pinned
  Linux sender failed to build with GCC 16.
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
- [`nitro-sense-led-capability-split.md`](nitro-sense-led-capability-split.md):
  one four-zone allowlist authorized both static colors and a distinct,
  unproved firmware-effect path.
- [`nitro-control-backend-check-mode-preview.md`](nitro-control-backend-check-mode-preview.md):
  the out-of-tree safety stop originally hid the runtime backend landing from
  check mode; the preview now renders files without starting services.
- [`nitro-control-backend-runtime-validation.md`](nitro-control-backend-runtime-validation.md):
  physical end-to-end proof for the typed Nitro runtime privilege boundary.
- [`nitro-keyboard-idle-timeout.md`](nitro-keyboard-idle-timeout.md):
  AN515-55 lighting can idle off and wake on keypress without an exposed timeout ABI.
- [`nitro-control-backend-extra-fields.md`](nitro-control-backend-extra-fields.md):
  the privileged JSON protocol originally ignored fields outside the reviewed operation schema.

Author: [importriri](https://github.com/importriri).
