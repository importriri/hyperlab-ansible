# Playbook map

Use the broad targets for normal reconciliation. Use narrow playbooks only when
one concern needs to be inspected or repaired without touching the rest.

## Main targets

### `playbooks/preflight.yml`

Identifies and validates the laptop profile before boot or PCI policy is
rendered.

```bash
ansible-playbook playbooks/preflight.yml
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
8. Hyperlab image-store layout.

```bash
ansible-playbook playbooks/foundation.yml --check --diff
ansible-playbook playbooks/foundation.yml
ansible-playbook playbooks/foundation.yml   # expected: changed=0
```

Use this target for a blind host, storage validation or early recovery.

### `playbooks/lab.yml`

Builds the intended laptop laboratory. It imports `foundation.yml`, then adds the
local desktop and Looking Glass host transport.

```bash
ansible-playbook playbooks/lab.yml --check --diff
ansible-playbook playbooks/lab.yml
ansible-playbook playbooks/lab.yml          # expected: changed=0
```

`lab.yml` deliberately does not create, reset or destroy VMs. Those operations
consume private image state, capacity and exact lifecycle confirmations; they
remain explicit transactions.

## Narrow host reconciliation

- `kvm-host.yml` — base plus headless KVM only.
- `image-store.yml` — validate stage-1 storage and reconcile the empty layout.
- `network-domains.yml` — reconcile only the five libvirt networks.
- `desktop.yml` — reconcile the cockpit on the host and listed workstation VMs.
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
ansible-playbook playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/debian-dev.yml \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'
```

Creation remains separate from `lab.yml` because a rerun of the host target must
never imply a workload lifecycle decision.

## Service lifecycle

1. reconcile `network-domains.yml`;
2. register the service with `service-register.yml`;
3. create its VM through `vm-create.yml`;
4. configure the application playbook, currently `jellyfin.yml`;
5. use offline `service-backup.yml` and `service-restore.yml` for recovery.

Unregister, restore, backup deletion and forced VM actions require exact
confirmations. The reason is ownership: automation may remove only state whose
identity is unambiguous.

## Developer and validation tools

- `dev.yml` configures a listed workstation guest with the desktop and IDE.
- `./verify.sh` mirrors the full CI discovery locally.
- `tests/render.yml` verifies generated configuration without touching the host.

The release campaign uses the frozen exact commits documented in
[`roadmap.md`](roadmap.md).
