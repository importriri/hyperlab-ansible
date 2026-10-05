# Security policy

## Reporting a vulnerability

Report a vulnerability privately through GitHub's private vulnerability
reporting:
<https://github.com/importriri/hyperlab-ansible/security/advisories/new>.
Do not open a public issue for it.

Please include what you found, the commit you tested, how to reproduce it,
and what an attacker gains. A report that crosses one of the boundaries in
[`docs/threat-model.md`](docs/threat-model.md) (a guest reaching another
network, the host, the GPU out of order, another Machine's data, or the
host's privilege) is the most useful kind.

## Scope

In scope: this repository's roles, playbooks, tools, the HyperLab shell and
the host-side bridges. Out of scope: vulnerabilities in KVM, QEMU, libvirt,
Hyprland, Quickshell, Looking Glass or the distributions themselves; report
those upstream, and tell us if HyperLab's use of them makes things worse.

HyperLab does not provide Qubes OS security properties; what it does and
does not protect against is in [`docs/threat-model.md`](docs/threat-model.md).
Known open problems are listed there.

## Supported versions

Only the latest `main` is supported.
