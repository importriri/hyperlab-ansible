# privatestack-ansible

[![ci](https://github.com/importriri/privatestack-ansible/actions/workflows/ci.yml/badge.svg)](https://github.com/importriri/privatestack-ansible/actions/workflows/ci.yml)

Ansible configuration for the Arch/KVM/VFIO laptop built by
[arch-bootstrap](https://github.com/importriri/arch-bootstrap).

The default target is a headless hypervisor. The local Sway desktop, Emacs
workstation setup and Looking Glass host transport are separate playbooks and
are never pulled in by the base lab playbook.

This is stage 2 of a three-repository project:

```text
arch-bootstrap  ->  privatestack-ansible  ->  arch-hypervisor-lab
base install        host configuration        design notes and test records
```

## What `main` configures

| Role | Purpose |
|---|---|
| `base` | Admin account, sudoers validation, sysctls and basic packages |
| `hardware_probe` | Selects the Nitro RTX 3060 or Predator RTX 3070 profile and validates PCI devices |
| `kvm_host` | Headless QEMU/libvirt installation with socket activation |
| `image_store` | Validates and prepares `/var/lib/libvirt/images` without creating images or domains |
| `vfio_boot` | Renders the systemd-boot profiles and reads the LUKS UUID at runtime |
| `network_domains` | Creates four NAT networks and one isolated lab network |
| `lab_isolation` | Loads the nftables rules that block cross-domain forwarding |
| `gpu_handoff` | Controls which workload domain may receive the dGPU |
| `desktop` | Optional Sway session with waybar, rofi, foot and the local shell setup |
| `dev_ide` | Optional Emacs/eglot workstation setup for guests |
| `looking_glass` | Optional kvmfr module, permissions and pinned client build |
| `brick_guard` | Checks role prerequisites and records completed roles |

VM lifecycle, image sealing and service roles are intentionally not published
on `main` yet. They remain local until their hardware checks are complete.

## Host model

The base host stays TTY-only and runs the virtualization layer, network
isolation and GPU hand-off. Applications and private services belong in VMs.
The interactive desktop is an opt-in administration interface on the iGPU; it
is not required for the headless target.

The repository contains profiles for:

- Acer Nitro 5, RTX 3060 Mobile;
- Acer Predator Helios 300, RTX 3070 Mobile.

The profile data is documented in
[`docs/hardware-profiles.md`](docs/hardware-profiles.md). A profile being
present does not by itself mean the full install has passed on that laptop.

## Run

On a freshly installed host, run the first pass as root because the `base` role
creates the normal administrator account:

```bash
pacman -S --needed git ansible
git clone https://github.com/importriri/privatestack-ansible.git
cd privatestack-ansible

ansible-playbook playbooks/preflight.yml
ansible-playbook playbooks/lab.yml --check --diff
ansible-playbook playbooks/lab.yml
passwd sid
```

Later runs can use:

```bash
ansible-playbook playbooks/lab.yml --ask-become-pass
```

A second run after a successful apply should report `changed=0`.

Optional playbooks:

```bash
ansible-playbook playbooks/desktop.yml --ask-become-pass
ansible-playbook playbooks/dev.yml --ask-become-pass
ansible-playbook playbooks/looking-glass.yml --ask-become-pass
```

The Windows side of Looking Glass remains manual because it installs a signed
Windows executable. The guest steps are in
[`arch-hypervisor-lab/configs/looking-glass.md`](https://github.com/importriri/arch-hypervisor-lab/blob/main/configs/looking-glass.md).

## Repository layout

```text
group_vars/all/   shared identity, boot, network and hardware data
playbooks/        entry points
roles/            one role per host function
schemas/          image and VM specification schemas
images/           image manifests; image files never enter Git
vm-specs/         example VM specifications
docs/adr/         design decisions
tests/            render, refusal and protocol checks
```

A new role needs its own playbook, prerequisite entry, `brick_guard` stamp and
tests. In [`group_vars/all/bricks.yml`](group_vars/all/bricks.yml),
`brick_requires` is the dependency graph and `brick_playbooks` maps every role
to the playbook that installs it.

## Verification

Run the same discovery-based checks used by CI:

```bash
./verify.sh
```

The verification covers Ansible lint, playbook syntax, rendered configuration,
Python contract tests, ShellCheck and Bats suites when the corresponding files
are present. Deliberate failure cases are documented in
[`tests/MUTATIONS.md`](tests/MUTATIONS.md).

## License

[MIT](LICENSE)
