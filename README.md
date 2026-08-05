# privatestack-ansible

[![ci](https://github.com/importriri/privatestack-ansible/actions/workflows/ci.yml/badge.svg)](https://github.com/importriri/privatestack-ansible/actions/workflows/ci.yml)

Stage 2 of the HyperLab pipeline. `arch-bootstrap` creates the encrypted Arch
host; this repository turns it into the VFIO hypervisor, local cockpit and
private-service platform; `arch-hypervisor-lab` records the architecture and
hardware evidence.

The repository is built around one rule: **roles own mechanisms, checked-in
specs own intent, playbooks define the safe order**.

## Final target

The intended laptop result is:

- systemd-boot defaults to the managed **VFIO** entry;
- the dGPU belongs to declared VFIO guests, not the host desktop;
- the host uses its integrated GPU for Sway and Looking Glass;
- five libvirt domains separate clean, development, dirty, isolated-lab and
  service traffic;
- VM state lives below the storage contract produced by `arch-bootstrap`;
- Windows, Linux and service guests use one transactional lifecycle engine;
- applications run inside dedicated VMs, never as host services.

## Two operator targets

### Headless foundation

`playbooks/foundation.yml` reconciles everything required before a local
cockpit is useful:

`base → hardware profile → KVM → VFIO boot → networks → isolation → GPU guard → storage contract → image store`

Use it for a blind host, first storage validation or recovery.

### Interactive laboratory

`playbooks/lab.yml` imports the complete foundation, then adds:

`desktop → Looking Glass host transport`

This is the normal final target for Nitro and Predator. The narrow
`desktop.yml` and `looking-glass.yml` playbooks remain available for focused
maintenance.

### Local cockpit

The desktop role points `/usr/local/bin/hyperlabctl` at the local checkout
instead of copying repository code into the host. The same command drives the
Waybar status group, the Rofi action palette and the terminal panel:

```text
Mod+F1  action palette
Mod+F2  cockpit panel
Mod+F3  diagnostic report
```

`hyperlabctl status --json`, `hyperlabctl doctor` and `hyperlabctl actions`
remain usable without the graphical session. Unmanaged libvirt domains may use
the narrow direct start and shutdown helpers. A domain carrying the managed
HyperLab metadata must go through its lifecycle playbook; privileged or
destructive actions are displayed for review and are never executed directly
from Waybar or Rofi.

The surface and its refusal boundary are recorded in
[`ADR 0014`](docs/adr/0014-cockpit-surface.md).

## Clean-install order

A fresh installation must come from the matching published `arch-bootstrap`
commit on `main` and its public `bash bootstrap` entrypoint. Stage 1 writes
`/etc/privatestack/bootstrap-storage.yml` only after the mounted VM store passes
its mapper, Btrfs root and `+C` checks.

### Fast path after the first boot

Use this path on a supported Nitro or Predator after `arch-bootstrap` completes.
Every Ansible playbook uses privilege escalation, so the manual commands include
`-K` and ask for the sudo password once per run.

```bash
git clone https://github.com/importriri/privatestack-ansible.git
cd privatestack-ansible
ansible-galaxy collection install -r collections/requirements.yml
ansible-playbook -K playbooks/preflight.yml
ansible-playbook -K playbooks/lab.yml --check --diff
ansible-playbook -K playbooks/lab.yml
ansible-playbook -K playbooks/lab.yml   # must end with changed=0
./verify.sh
```

This builds the complete host target only. Image imports and VM lifecycle actions
remain separate because they can create, reset or destroy private workload state.
The detailed steps below explain each command and the supported recovery paths.

### 1. Clone stage 2

```bash
# Fetch the published stage-2 repository.
git clone https://github.com/importriri/privatestack-ansible.git

# Enter the repository so every relative path resolves against the checked-out tree.
cd privatestack-ansible

# Install the Ansible collections pinned by the repository contract.
ansible-galaxy collection install -r collections/requirements.yml
```

### 2. Validate the laptop profile

```bash
# Detect and validate the Nitro or Predator profile without changing the host.
ansible-playbook -K playbooks/preflight.yml
```

PCI IDs come from the matching Nitro or Predator profile. They are not copied
into commands or public VM manifests.

### 3. Build the headless foundation

```bash
# Preview the headless foundation and display the managed diff.
ansible-playbook -K playbooks/foundation.yml --check --diff

# Apply the complete headless foundation.
ansible-playbook -K playbooks/foundation.yml

# Prove idempotence; this pass must report changed=0.
ansible-playbook -K playbooks/foundation.yml
```

The third command must report `changed=0`. A missing or mismatched bootstrap
storage contract stops the run before the HyperLab image tree is created.

An already validated legacy Nitro host may adopt its observed mount once,
without repartitioning or remounting:

```bash
# Inspect the existing mount and print the exact one-time confirmation.
ansible-playbook -K playbooks/bootstrap-storage-adopt.yml --check --diff

# Write only the storage contract; replace the placeholder with check-mode output.
ansible-playbook -K playbooks/bootstrap-storage-adopt.yml --diff \
  -e bootstrap_storage_confirm_adopt='adopt:/var/lib/libvirt/images:<observed-mapper>'
```

Fresh machines do not use adoption; they receive the contract from
`arch-bootstrap`.

### 4. Prepare and seal images

Images are explicit transactions because Windows bytes and workshop evidence
are private, while public cloud images require independently pinned checksums.

```bash
# Preview import of the pinned official Arch cloud image.
ansible-playbook -K playbooks/image-prepare.yml --check --diff \
  -e image_factory_manifest=images/arch.yml

# Acquire, inspect and commit the image transaction.
ansible-playbook -K playbooks/image-prepare.yml \
  -e image_factory_manifest=images/arch.yml

# Revalidate the sealed base without replacing it.
ansible-playbook -K playbooks/image-validate.yml \
  -e image_factory_manifest=images/arch.yml
```

Windows first follows [`docs/windows-image-workshop.md`](docs/windows-image-workshop.md) and passes through `playbooks/windows-workshop.yml`; the resulting private qcow2 is then imported through `image-prepare.yml`. Distributions published only as installer media use the local qcow2 hand-off in [`docs/linux-iso-workshop.md`](docs/linux-iso-workshop.md). A prepared base is finished with `playbooks/image-validate.yml`.

### 5. Reconcile the complete laptop lab

```bash
# Preview the complete laptop target: foundation, Sway and Looking Glass host side.
ansible-playbook -K playbooks/lab.yml --check --diff

# Apply the complete laptop target.
ansible-playbook -K playbooks/lab.yml

# Prove idempotence; this pass must report changed=0.
ansible-playbook -K playbooks/lab.yml
```

The last pass must report `changed=0`. `lab.yml` includes the desktop and
Looking Glass host side because they are part of the intended laptop workflow,
not optional documentation examples.

The signed Windows Looking Glass application, virtual display and interactive
Windows account setup remain guest-side manual steps. Host automation cannot
safely infer or redistribute them.

### 6. Create workloads deliberately

VM lifecycle stays outside `lab.yml`. A host update must never imply create,
reset, stop or destroy decisions for private workloads.

```bash
# Preview a cloud-init Linux transaction with a host-local public key.
ansible-playbook -K playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/debian-dev.yml \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'

# Create the declared Windows workload from its sealed private base.
ansible-playbook -K playbooks/vm-create.yml \
  -e guest_spec=vm-specs/win11clean-valley.yml
```

The disposable Arch release-gate guest uses the same lifecycle boundary:

```bash
# Resolve the declared Arch image import to a quoted Ansible command.
hyperlabctl actions --resolve image.import --manifest images/arch.yml

# Resolve creation of the disposable storage-gate guest.
hyperlabctl actions --resolve vm.create --spec vm-specs/arch-bootstrap-gate.yml

# Resolve the lifecycle-managed start command for that guest.
hyperlabctl actions --resolve vm.managed-start --spec vm-specs/arch-bootstrap-gate.yml
```

`hyperlabctl` resolves checked-in targets to quoted commands; Ansible performs the
privileged image and VM transactions. The Arch base is the versioned official
arch-boxes cloud image, while the instance disk is grown to 20 GiB for the
storage gate.

Standard and VFIO specs use the same planner, locks, capacity checks, provenance
chain and rollback boundary. Forced stop, reset and destruction require exact
confirmations.

### 7. Register services before creating them

```bash
# Preview registration and its identity, lease and memory reservations.
ansible-playbook -K playbooks/service-register.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml

# Commit the service registration.
ansible-playbook -K playbooks/service-register.yml \
  -e service_spec=service-specs/svc-jellyfin.yml

# Create the registered service VM with a host-local public key.
ansible-playbook -K playbooks/vm-create.yml \
  -e guest_spec=vm-specs/svc-jellyfin.yml \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'

# Configure Jellyfin inside the service guest, never on the hypervisor.
ansible-playbook -K playbooks/jellyfin.yml
```

Registration owns the service identity, static lease, inactive RAM reservation
and offline recovery policy before the VM exists.

### 8. Verify the repository contract

```bash
sudo pacman -S ansible-lint ruff shellcheck bats
ansible-galaxy collection install -r collections/requirements.yml
./verify.sh
```

`verify.sh` names every missing tool at once and refuses to start rather than
reporting a green run with steps that never executed.

CI and `verify.sh` discover every playbook, structural contract, refusal suite,
schema mutation, render test, Bats protocol, shell script and Python file. CI
proves the software contract; Nitro and Predator prove frozen commits on real
hardware.

One discovered contract can legitimately do nothing:
`tests/cross_repo_contract.py` needs an `arch-hypervisor-lab` checkout and
skips loudly when it cannot find one. It is the CI job of the same name, which
checks out both repositories, that is not allowed to skip.

The focused Nitro boundary for the integrated desktop surface is automated by:

```bash
# Run the focused Nitro cockpit boundary and retain its local evidence.
./run-nitro-m9-cockpit-gate.sh
```

It records the repository battery, network and desktop idempotence, action
registry, event stream and the intentionally refused unsealed-image create.
Only the printed Sway/Waybar checks remain interactive.

### 9. Run the evidence campaign

The final campaign is not a checklist edited by hand. M9 creates a canonical
plan, a mode-`0600` evidence scaffold and ordered gate records:

```text
release_acceptance.py   plan → scaffold → record → status → seal
release_probe.py        storage, Ansible recap and typed file/scalar evidence
```

Start with [`docs/release-evidence.md`](docs/release-evidence.md). It contains the
exact Nitro-first command order, the disposable two-disk gate, the Predator
reuse rule and the milestone merge boundary.

## Why VM creation is not inside `lab.yml`

A single all-powerful playbook looks convenient but creates the wrong safety
boundary:

- image sealing may need private local input and operator-confirmed hashes;
- VFIO start depends on current GPU ownership and available memory;
- reset and destruction are lifecycle decisions, not host configuration;
- service VMs must be registered before their disks and domains exist.

`lab.yml` therefore owns the **complete host target**. Workload playbooks own
**explicit transactions**. This gives one clear installation path without
turning every host reconciliation into a workload event.

## Repository map

- [`docs/playbooks.md`](docs/playbooks.md) — playbooks grouped by operator intent
  and the commands that belong together.
- [`docs/brick-catalog.md`](docs/brick-catalog.md) — roles grouped by the
  responsibility they protect, without a flat status table.
- [`docs/desktop.md`](docs/desktop.md) — Sway controls, resident HyperLab
  surfaces, themes, wallpapers and fallback behavior.
- [`docs/adr/README.md`](docs/adr/README.md) — ordered architecture decisions
  and their current supersession state.
- [`docs/historical-audit-m0.md`](docs/historical-audit-m0.md) — the linked,
  explicitly historical baseline from before VM lifecycle work.
- [`docs/release-evidence.md`](docs/release-evidence.md) — frozen commits,
  probe-driven evidence and ordered merge gates.
- [`docs/roadmap.md`](docs/roadmap.md) — stacked milestones and final hardware
  campaign.
- [`docs/adr/`](docs/adr/) — decisions and rejected alternatives.
- [`docs/hardware-profiles.md`](docs/hardware-profiles.md) — Nitro and Predator
  profile boundaries.
- [`docs/network-reconciliation.md`](docs/network-reconciliation.md) — network
  ownership and drift handling.
- [`docs/service-vm-contract.md`](docs/service-vm-contract.md) — service
  registration, backup and restore.
- [`docs/service-slots.md`](docs/service-slots.md) — intentionally inert future
  service identities and the conditions required before activation.
- [`docs/jellyfin-appliance.md`](docs/jellyfin-appliance.md) — the reference
  guest appliance and lifecycle-bound exposure contract.
- [`docs/windows-image-workshop.md`](docs/windows-image-workshop.md) — the
  temporary virt-manager boundary, Windows evidence and sealing order.
- [`docs/linux-iso-workshop.md`](docs/linux-iso-workshop.md) — ISO installation
  media converted into a local qcow2 transaction.
- [`tests/MUTATIONS.md`](tests/MUTATIONS.md) — deliberate contract breakage used
  to prove that the verification battery fails closed.
- [`tools/hyperlabctl/README.md`](tools/hyperlabctl/README.md) — cockpit command
  surface, provider boundaries and terminal usage.

Policy data lives under `group_vars/all/`, image manifests under `images/`, VM
instances under `vm-specs/`, service ownership under `service-specs/`, and
schemas under `schemas/`. Disk images, credentials, signed guest binaries and
host-local PCI addresses never enter Git.

## Development rule

One brick does one job. Comments explain **why a boundary exists**; module names
and upstream documentation already explain mechanics. A new brick needs:

1. one role;
2. one narrow playbook or a deliberate place in a broad target;
3. declared prerequisites in `group_vars/all/bricks.yml`;
4. executable contracts that prove its refusal and ownership boundaries.

## License

[MIT](LICENSE)
