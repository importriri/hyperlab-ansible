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

Author: [importriri](https://github.com/importriri).
