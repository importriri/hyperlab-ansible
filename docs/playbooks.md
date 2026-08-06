# Playbook map

Use the broad targets for normal reconciliation. Use narrow playbooks only when
one concern needs to be inspected or repaired without touching the rest.

## Main targets

### `playbooks/preflight.yml`

Identifies and validates the laptop profile before boot or PCI policy is
rendered.

```bash
# Detect and validate one reviewed hardware profile without changing the host.
ansible-playbook -K playbooks/preflight.yml
```

### `playbooks/foundation.yml`

Builds the complete headless host target:

1. administrative base;
2. hardware profile;
3. KVM/libvirt;
4. VFIO-first boot entries;
5. network domains and isolation;
6. GPU handoff policy;
7. stage-1 storage validation;
8. HyperLab image-store layout.

```bash
# Preview the complete headless foundation and display the managed diff.
ansible-playbook -K playbooks/foundation.yml --check --diff

# Apply the complete headless foundation.
ansible-playbook -K playbooks/foundation.yml

# Prove immediate idempotence; this pass must report changed=0.
ansible-playbook -K playbooks/foundation.yml
```

Use this target for a blind host, storage validation or early recovery.

### `playbooks/lab.yml`

Builds the intended laptop laboratory. It imports `foundation.yml`, then adds the
local host Sway cockpit and Looking Glass host transport.

```bash
# Preview foundation, Sway and Looking Glass host transport.
ansible-playbook -K playbooks/lab.yml --check --diff

# Apply the complete laptop target.
ansible-playbook -K playbooks/lab.yml

# Prove immediate idempotence; this pass must report changed=0.
ansible-playbook -K playbooks/lab.yml
```

`lab.yml` deliberately does not create, reset or destroy VMs. Those operations
consume private image state, capacity and exact lifecycle confirmations; they
remain explicit transactions.

## Narrow host reconciliation

- `kvm-host.yml` — base plus headless KVM only.
- `image-store.yml` — validate stage-1 storage and reconcile the empty layout.
- `bootstrap-storage-adopt.yml` — take over a VM store that was already
  validated by hand, without touching the storage itself. It exists so that
  a machine set up before this pipeline does not have to be rebuilt to join
  it.
- `network-domains.yml` — reconcile only the five libvirt networks.
- `host-desktop-sway.yml` — reconcile the Sway cockpit on the physical host only.
- `looking-glass.yml` — reconcile only the host-side Looking Glass transport.

These playbooks are maintenance tools, not an alternative installation order.

## Image provenance

- `windows-workshop.yml` records privacy-safe evidence for one Windows master.
- `image-prepare.yml` acquires or imports one image transaction.
- `image-validate.yml` validates an already sealed image without replacing it.

Every image starts in check mode. Public manifests stay `not-built` until the
operator commits reviewed checksum and provenance evidence. Interactive source
builds are documented in [`windows-image-workshop.md`](windows-image-workshop.md)
and [`linux-iso-workshop.md`](linux-iso-workshop.md); virt-manager stops at the
workshop boundary and never owns a managed domain.

## VM lifecycle

The same playbooks serve standard and VFIO specs:

- `vm-validate.yml`
- `vm-create.yml`
- `vm-start.yml`
- `vm-shutdown.yml`
- `vm-stop.yml`
- `vm-reset.yml`
- `vm-destroy.yml`

Pass exactly one checked-in spec:

```bash
# Preview one standard guest transaction with a host-local SSH public key.
ansible-playbook -K playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/debian-dev.yml \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'
```

[`vm-specs/arch-dev.yml`](../vm-specs/arch-dev.yml) is the permanent Arch
development-workstation example. It consumes the same standard lifecycle
engine as every other guest.

Creation remains separate from `lab.yml` because a rerun of the host target must
never imply a workload lifecycle decision.

### Arch development resource profiles

`arch-dev` defaults to the reviewed `balanced` profile: 8 GiB and four vCPUs.
The same checked-in spec can select the `heavy` profile, 16 GiB and four vCPUs,
without changing disk, lifecycle, network or device trust:

```bash
ansible-playbook -K playbooks/vm-create.yml \
  -e guest_spec=vm-specs/arch-dev.yml \
  -e guest_resource_profile=heavy \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'
```

The selected profile is written into managed VM state. Validation therefore
refuses a later run that silently selects different resources.

## Service lifecycle

1. `network-domains.yml` reconciles the five network identities.
2. `service-register.yml` reserves service identity, lease and inactive RAM.
3. `service-validate.yml` checks the committed registration without changing it.
4. `vm-create.yml` creates the registered service VM from its checked-in spec.
5. `jellyfin.yml` configures the reference application inside that guest.
6. `service-backup.yml` and `service-restore.yml` perform offline recovery.
7. `service-delete-backup.yml` removes only one exactly confirmed owned backup.
8. `service-unregister.yml` releases an exactly confirmed inactive service.

Unregister, restore, backup deletion and forced VM actions require exact
confirmations. The reason is ownership: automation may remove only state whose
identity is unambiguous.

## Developer and validation tools

- `guest-arch-hyprland.yml` builds the reusable Arch Hyprland workstation.
- `guest-arch-dev.yml` adds the development stack to that workstation.
- `guest-gpu-nvidia.yml` is the narrow post-passthrough NVIDIA driver target.
- `guest-looking-glass-linux.yml` builds the pinned experimental PipeWire sender
  but never starts or enables it.
- `guest-arch-dev-vfio.yml` assembles the full accelerated development guest,
  but refuses to install the driver until an NVIDIA PCI function is visible.
  Its boundary and remaining hardware gates are documented in
  [`arch-dev-acceleration.md`](arch-dev-acceleration.md).
- `dev.yml` remains a compatibility entrypoint for `guest-arch-dev.yml`.
- `./verify.sh` mirrors the full CI discovery locally.
- `tests/render.yml` verifies generated configuration without touching the host.

The release campaign uses the frozen exact commits documented in
[`roadmap.md`](roadmap.md).

## Private guest wallpaper injection

`guest-visual-assets.yml` is an explicit guest-only transaction. It accepts one
HTTPS bundle URL and its reviewed SHA-256 digest. The controller downloads the
bundle below its runtime directory, copies it into private guest staging,
validates every manifest path and image digest, installs the four theme pools,
and removes both temporary copies even when installation fails.

No wallpaper binary is committed to this repository or retained on the physical
host. The installed guest keeps between one and twenty sequential PNG files per
surface (`01.png` through `20.png`). Every theme must provide separate desktop
and lockscreen content; the generated bootstrap images remain offline fallbacks.

The bundle root contains `guest-wallpapers.v1.yml` and this layout:

```text
wallpapers/<theme>/desktop/NN.png
wallpapers/<theme>/lockscreen/NN.png
```

Apply only after `guest-arch-hyprland.yml` has landed:

```bash
ansible-playbook -i inventory.ini playbooks/guest-visual-assets.yml \
  -e guest_visual_assets_bundle_url=https://assets.example/private.tar.zst \
  -e guest_visual_assets_bundle_sha256=<reviewed-lowercase-sha256>
```
