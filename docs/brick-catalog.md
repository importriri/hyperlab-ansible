# Brick catalog

Bricks are grouped by the decision they protect. This catalog explains why a
brick exists; task files remain the source for implementation details.

## Host foundation

- **`base`** establishes the administrative identity and the minimum host
  hardening expected by every later stage.
- **`hardware_probe`** selects a reviewed laptop profile so PCI identities never
  become copy-pasted operator input.
- **`kvm_host`** installs the headless libvirt/KVM foundation. Desktop packages
  do not belong in this layer because the same foundation must work without a
  local cockpit.
- **`vfio_boot`** renders the managed boot profiles and makes VFIO the normal
  laboratory path. Host graphics and recovery remain explicit alternatives.
- **`network_domains`** owns the five libvirt networks and their stable identity.
- **`lab_isolation`** enforces the cross-domain drop policy independently from
  libvirt's generated NAT rules.
- **`gpu_handoff`** gives the dGPU to exact reviewed domain names and prevents a
  lower-trust guest from handing it upward without reboot.

## Storage and provenance

- **`bootstrap_storage`** checks that stage 1 and stage 2 agree on mapper,
  mountpoint, Btrfs root and inherited `+C` before VM data is written.
- **`image_store`** creates only the verified directory layout. It never imports
  images or defines domains.
- **`windows_workshop`** binds privacy-safe guest evidence to a Windows image
  policy without storing accounts, paths or signed binaries in Git.
- **`image_factory`** acquires or imports bytes, verifies qcow2 properties and
  commits provenance only after the complete transaction passes.

## Workload lifecycle

- **`guest`** is the single lifecycle engine for standard and VFIO domains. It
  owns deterministic identity, capacity checks, locks, rollback and destructive
  confirmations.
- VM specs remain separate from the role because instances are policy data, not
  another implementation of the lifecycle.

## Interactive cockpit

- **`host_desktop_sway`** provides the local Sway cockpit. It is part of the final laptop
  target but remains separate from the headless foundation.
- **`looking_glass`** installs only the host transport and client. The signed
  Windows application and virtual display remain private guest work.
- **`workstation_kernel`** installs and proves the reviewed guest kernel profile
  before removing a recovery kernel.
- **`workstation_access`** makes the unprivileged graphical account usable while
  keeping direct root authentication disabled.
- **`guest_desktop_hyprland`** provides the guest-only Hyprland shell and removes
  legacy host-cockpit artefacts from migrated workstations.
- **`guest_visual_assets`** verifies and injects private wallpaper pools through
  ephemeral controller and guest staging; no asset remains on the host.
- **`guest_gpu_nvidia`** installs the official open NVIDIA DKMS and Wayland stack
  only after a passed NVIDIA PCI function is visible inside the guest.
- **`guest_looking_glass_linux`** builds the pinned upstream PipeWire sender as
  an explicit, disabled-by-default Linux experiment; hardware decides whether a
  fork is needed.
- **`dev_ide`** adds the pinned editor and language-server stack after the guest
  desktop is present; it is never a host dependency.

## Service ownership

- **`service_registry`** reserves service identity and RAM before VM creation and
  owns offline backup/restore policy.
- **`service_exposure`** opens only reviewed LAN paths while the matching service
  VM is active.
- **`jellyfin`** is the reference guest application. It runs inside
  `svc-jellyfin`, never on the hypervisor.
- Nextcloud, Vaultwarden, Immich and Pi-hole remain inert slots until each has a
  complete VM, recovery and exposure contract.

## Contract infrastructure

- **`brick_guard`** refuses missing prerequisites using the central dependency
  graph. An unknown or unstamped dependency must never behave like an empty
  list.

The dependency data lives in
[`group_vars/all/bricks.yml`](../group_vars/all/bricks.yml). The operator-facing
playbook map lives in [`playbooks.md`](playbooks.md).
