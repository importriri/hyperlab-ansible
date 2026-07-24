# privatestack-ansible

[![ci](https://github.com/importriri/privatestack-ansible/actions/workflows/ci.yml/badge.svg)](https://github.com/importriri/privatestack-ansible/actions/workflows/ci.yml)

A warehouse of pre-configured Ansible bricks for the host that
[arch-bootstrap](https://github.com/importriri/arch-bootstrap) builds.
One brick does one job. Playbooks are the assembly instructions.

Part of a trilogy:
[arch-bootstrap](https://github.com/importriri/arch-bootstrap) installs the
encrypted base system, **privatestack-ansible** (this repo) turns it into a
segmented hypervisor and a private services stack, and
[arch-hypervisor-lab](https://github.com/importriri/arch-hypervisor-lab)
documents the lab that drove the design.

## The iron principle: empty, blind, secure host

The host runs nothing of its own except the hypervisor plumbing: libvirt,
the network domains, the nftables isolation, the GPU guard. TTY-only, no
GUI, no listening services, minimal attack surface. **Every service runs in
a dedicated VM on its own domain** — never a container on the host, never a
package on the host. The host stays a fortress; the services stay cattle.

## Brick catalog

| Brick | Job | Kind | Status |
|---|---|---|---|
| `base` | Admin user, validated sudoers drop-in, hardening sysctls, pacman QoL | lab bundle (1/6) | available |
| `kvm_host` | Headless KVM stack, socket activation, `/dev/kvm` guard | lab bundle (2/6) | available |
| `vfio_boot` | The four systemd-boot entries, templated; LUKS UUID read at runtime | lab bundle (3/6) | available |
| `network_domains` | The five libvirt networks (four NAT + isolated lab) | lab bundle (4/6) | available |
| `lab_isolation` | The nftables cross-domain drop matrix | lab bundle (5/6) | available |
| `gpu_handoff` | Trust-ranked GPU handoff hook, fail-closed | lab bundle (6/6) | available |
| `desktop` | Sway + ly cockpit: Mocha rice (floating waybar, rofi launcher + power menu, cava strip), shell nav kit | optional | available |
| `dev_ide` | Emacs IDE: eglot LSP (java/js/html/css/bash/ansible) + Claude Code | optional (guests) | available |
| `looking_glass` | kvmfr transport, node permissions, client pinned to a build | optional (host) | available |
| `guest` | The VM foundation: verified cloud image, qcow2 overlay, cloud-init seed | foundation | planned — A8 |
| `jellyfin` | Private media server — the reference optional brick | optional | planned — A9 |
| `nextcloud` | Private drive | optional | documented slot |
| `vaultwarden` | Password manager | optional | documented slot |
| `immich` | Private photo library | optional | documented slot |
| `pihole` | Filtering DNS | optional | documented slot |

Bricks land stage by stage; this table is the truth about what exists.

The cockpit is opt-in: `playbooks/desktop.yml` mounts the desktop on the
host or on any VM in `workstations` (the host rides its free iGPU — the
dGPU belongs to `gpu_handoff`); `playbooks/dev.yml` turns a guest into a
dev workstation — same cockpit plus the Emacs IDE wired to eglot and
Claude Code (`claude` authenticates on first run: manual, by design);
`playbooks/looking-glass.yml` adds the window onto the GPU VM — the kvmfr
transport, the node permissions QEMU and the desktop session both need, and
the client built from a pinned commit. Its guest half stays manual by design
and is documented in
[arch-hypervisor-lab](https://github.com/importriri/arch-hypervisor-lab/blob/main/configs/looking-glass.md):
a signed .exe is not a brick.
The lab bundle never mounts any of them — the blind host stays the default.

## Assembly

On a freshly bootstrapped host (first run as root, since the admin user is
one of the things `base` creates):

```
pacman -S --needed git ansible
git clone https://github.com/importriri/privatestack-ansible.git
cd privatestack-ansible

# dress rehearsal first, always
ansible-playbook playbooks/lab.yml --check --diff

# the real run
ansible-playbook playbooks/lab.yml

# base created your admin user with a locked password - claim it
passwd sid
```

Subsequent runs as the admin user: `ansible-playbook playbooks/lab.yml
--ask-become-pass`. A second run right after the first must report
`changed=0` — that is the definition of done.

The shared contract lives in [`group_vars/all.yml`](group_vars/all.yml):
identity, boot values matching what arch-bootstrap produced, the five
network domains, the GPU trust map, and the LAN exposure allowlist. Bricks
consume the contract; they never redefine it.

## The extension contract

Adding a brick is a mechanical gesture:

1. `roles/<name>/` — the brick, one job;
2. `playbooks/<name>.yml` — its assembly instructions;
3. one row in the catalog table above.

Nothing central gets edited. CI discovers the new playbook by itself,
syntax-checks it, lints the role, and runs the brick's tests if it ships
any. If adding a brick ever requires more than this, that is an
architecture bug and gets treated as one.

## Testing

Locally, the whole battery is one command from the repo root: `./verify.sh`
(it mirrors CI by discovery, and doubles as a git pre-commit hook:
`ln -s ../../verify.sh .git/hooks/pre-commit`).

Every push runs, via discovery:

- **`ansible-lint`** on the whole repo, production profile — FQCN, explicit
  modes, `changed_when` on read-only commands, role-prefixed variables;
- **syntax-check** on every playbook in `playbooks/`;
- **`tests/render.yml`** — invariant tests: shipped and generated files are
  validated against the properties that past bugs paid for (the sudoers
  drop-in must pass `visudo -cf`, `rp_filter` must be loose, the lab domain
  must be the only isolated one, the GPU rotation must never include
  `services`, ...). The suite grows with every brick;
- **`bats`** protocol suites and **`shellcheck`**, when a brick ships shell.
The whole battery runs locally in one shot: **`./verify.sh`** - the
same levels CI runs, by discovery, correct at every stage of the repo,
and usable as a pre-commit hook. And because a test that has never
been seen red proves nothing, [`tests/MUTATIONS.md`](tests/MUTATIONS.md)
catalogs fifteen deliberate breakages - one per invariant - with the
exact command, the check expected to turn red, and the restore.
Replay one before you push.

## License

[MIT](LICENSE)
