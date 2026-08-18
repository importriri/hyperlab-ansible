# hyperlab-ansible

[![ci](https://github.com/importriri/hyperlab-ansible/actions/workflows/ci.yml/badge.svg)](https://github.com/importriri/hyperlab-ansible/actions/workflows/ci.yml)

Stage 2 of HyperLab. `arch-bootstrap` installs the encrypted Arch host; this
repository turns that host into the KVM/VFIO laptop lab and owns explicit image,
VM and service transactions. `arch-hypervisor-lab` records architecture, failure
writeups and hardware evidence.

The physical host stays small. Sway runs on the iGPU, the NVIDIA dGPU is reserved
for VFIO workloads, and services live in VMs rather than on the hypervisor.

## Start here

Use a clean `arch-bootstrap` install, then run stage 2 from its repository root:

```bash
git clone https://github.com/importriri/hyperlab-ansible.git
cd hyperlab-ansible
ansible-galaxy collection install -r collections/requirements.yml
./verify.sh
ansible-playbook -K playbooks/preflight.yml
ansible-playbook -K playbooks/lab.yml --check --diff
ansible-playbook -K playbooks/lab.yml
ansible-playbook -K playbooks/lab.yml
```

The last run must report `changed=0`. A successful CI run is a software result;
hardware support is recorded separately in `arch-hypervisor-lab`.

For a complete Nitro walkthrough, including images, workloads, VFIO and Looking
Glass, follow the `arch-hypervisor-lab/SETUP.md` guide.

### Fast path after the first boot

After the first successful application, the routine reconciliation path is:

```bash
ansible-playbook -K playbooks/preflight.yml
ansible-playbook -K playbooks/lab.yml --check --diff
ansible-playbook -K playbooks/lab.yml
ansible-playbook -K playbooks/lab.yml   # must end with changed=0
```

## What `lab.yml` owns

`lab.yml` is the normal laptop target. It applies the headless foundation first,
then the local Sway desktop, then the Looking Glass host transport. That order is
intentional: Looking Glass is part of the interactive desktop path and must not
become a hidden prerequisite of the recovery host.

`playbooks/lab.yml` imports the complete foundation before adding the
interactive layer. The `host-desktop-sway.yml` and `looking-glass.yml` playbooks remain available for focused
maintenance, while hardware-specific experiments keep their own narrow
entrypoints.

The foundation owns:

- the reviewed Nitro or Predator hardware profile;
- KVM/libvirt and the stage-1 storage contract;
- VFIO boot policy and GPU ownership checks;
- the five trust-domain networks and host isolation;
- the HyperLab image-store layout.

The interactive target adds:

- Sway, Waybar and the compact HyperLab drawer;
- the full Control Center;
- the host-side Looking Glass/kvmfr transport.

## What stays explicit

Host reconciliation must not create or destroy private workloads. Image import,
VM creation, start, shutdown, reset, destruction, service registration and
recovery therefore remain separate playbooks with their own checks.

Windows installation, the Windows Looking Glass application and the Windows
virtual display also remain guest-side steps. Linux Looking Glass sender support
is still experimental and is not enabled as a persistent service.

## Optional hardware roles

| Role | Playbook | Boundary |
| --- | --- | --- |
| `nitro_sense` | `playbooks/nitro-sense.yml` | Native-first Acer Nitro thermal controls with an explicit, reversible Linuwu-Sense driver opt-in. |

`nitro_sense` is never imported by `foundation.yml` or `lab.yml`. It can replace
`acer_wmi`, so its refusal, recovery and hardware-test procedure is documented
separately in [`docs/nitro-sense.md`](docs/nitro-sense.md).

The dependency graph lives in [`group_vars/all/bricks.yml`](group_vars/all/bricks.yml). [`docs/brick-catalog.md`](docs/brick-catalog.md) explains why each brick exists and which prerequisite stamp protects its boundary; [`docs/playbooks.md`](docs/playbooks.md) maps those bricks to the operator entrypoints.

## Hardware status

The Acer Nitro 5 with RTX 3060 Mobile is the reference machine for the current
release work. Host VFIO and the accelerated Arch guest have real Nitro evidence.
The Linux Looking Glass video path has also been demonstrated end to end, while
final session-persistence and input-return checks remain open.

The Acer Predator Helios 300 with RTX 3070 Mobile has a reviewed profile, but it
does not become a full compatibility claim until the same frozen repository
commits that pass Nitro are replayed on Predator.

Current evidence belongs in `arch-hypervisor-lab`, not in role defaults.

## Repository map

- `playbooks/`: broad targets and explicit lifecycle transactions;
- `roles/`: one responsibility per role;
- `group_vars/all/`: shared policy and hardware-independent intent;
- `images/`: public image manifests and provenance policy;
- `vm-specs/`: declared workload instances;
- `service-specs/`: service identity and lifecycle ownership;
- `schemas/`: validated input contracts;
- `tests/`: refusal, render, schema and structural contracts;
- `docs/`: operator and architecture notes;
- `problems/`: failures that changed a contract or implementation.

Operator and architecture references:

- [`docs/desktop.md`](docs/desktop.md) — Sway controls, resident surfaces and themes;
- [`docs/hardware-profiles.md`](docs/hardware-profiles.md) — reviewed laptop boundaries;
- [`docs/network-reconciliation.md`](docs/network-reconciliation.md) — network ownership and drift handling;
- [`docs/arch-dev-acceleration.md`](docs/arch-dev-acceleration.md) — accelerated Arch guest policy;
- [`docs/nitro-control-backend.md`](docs/nitro-control-backend.md) — privileged Nitro broker boundary and runtime protocol;
- [`docs/nitro-arch-dev-vfio-campaign.md`](docs/nitro-arch-dev-vfio-campaign.md) — ordered Nitro VFIO campaign;
- [`docs/windows-image-workshop.md`](docs/windows-image-workshop.md) — Windows image sealing;
- [`docs/linux-iso-workshop.md`](docs/linux-iso-workshop.md) — ISO-to-qcow2 handoff;
- [`docs/service-vm-contract.md`](docs/service-vm-contract.md) — service registration and recovery;
- [`docs/service-slots.md`](docs/service-slots.md) — intentionally inert service identities;
- [`docs/jellyfin-appliance.md`](docs/jellyfin-appliance.md) — reference guest appliance;
- [`docs/release-evidence.md`](docs/release-evidence.md) — frozen commits and hardware gates;
- [`docs/roadmap.md`](docs/roadmap.md) — milestones and remaining campaigns;
- [`docs/historical-audit-m0.md`](docs/historical-audit-m0.md) — historical baseline before lifecycle work.

## Compatibility namespace

Some installed state still uses `/etc/privatestack`, `/var/lib/privatestack` and
older `privatestack-*` helper names. Those names are compatibility interfaces
consumed by the bootstrap contract, brick stamps and existing installations.
They are not the public project name and are not renamed casually. A future
namespace migration must read the old state, write the new state and prove a
safe upgrade path before the old paths are removed.

## Development rules

Roles own mechanisms. Checked-in data owns policy. Playbooks define order.
Comments should explain a boundary or a non-obvious failure mode, not narrate
what an Ansible module already says.

A change is not finished because a static test passes. Hardware claims require
the named laptop, the exact repository commits and the matching evidence gate.

## Author

[importriri](https://github.com/importriri) is the author and maintainer.

## License

[MIT](LICENSE)
