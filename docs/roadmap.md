# HyperLab roadmap

Work is divided into milestones so software checks, hardware validation and
publication stay separate. A green test suite proves repository behavior. A
hardware claim exists only after the matching gate runs on the named laptop.

## Current state

```text
M0   cockpit and audit                         complete
M1   image, VM and brick contracts             complete
M2   HyperLab image store                      complete
M3   standard guest lifecycle                  Nitro VM gate passed
M4   VFIO guest ownership                      software green; VM gate pending
M5   image acquisition and sealing             Arch path passed; private images pending
M6   Windows workshop                          software green; guest evidence pending
M7   service registration and recovery         software green; hardware gate pending
M8   Jellyfin reference appliance              software green; appliance gate pending
M9   release and evidence runner               software green; full campaign pending
M10  domain manager and VM composition         software green; live workload gate pending
M11  desktop shell and Control Center          Nitro visual/idempotence gate passed
M12  snapshots, backups and golden images      planned
M13  seamless guest applications               planned
```

“Software green” means the discovery-based verifier passed. It is not a
hardware claim. The exact commits used for Nitro and Predator evidence are
recorded by the M9 release runner.

## Host and lifecycle foundation

### M0 — cockpit and audit

Established the first Sway, Foot and input conventions and recorded the initial
architecture decisions.

### M1 — contracts

Separated hardware profiles from VM policy, added image manifests, VM specs,
memory budgets and the enforced brick dependency graph.

### M2 — image store

Defined the permissioned, NOCOW-aware storage layout below the stage-1 storage
contract. The Nitro gate proved QEMU/swtpm identities, directory traversal,
`+C` inheritance and second-run idempotence.

### M3 — standard guest lifecycle

Added deterministic planning, sealed-base checks, clone and overlay creation,
cloud-init, UEFI/TPM state, libvirt definition, capacity locking, reset and
destruction. The Nitro gate completed the disposable Arch two-loop storage test
without modifying the sealed base.

### M4 — VFIO guest ownership

Owns host-local PCI planning, exclusive GPU starts, Looking Glass/kvmfr,
recovery SPICE and trust-ranked handoff. The software contract is green; the
full guest lifecycle still needs its named hardware gate.

### M5 — image acquisition and sealing

Handles pinned public cloud images, private local imports, qcow2 inspection and
provenance receipts. The public Arch path has passed; private Windows and ISO
workshop outputs keep separate evidence.

### M6 — Windows workshop

Defines privacy-safe clean/dirty image preparation and binds workshop evidence
to image and guest provenance without committing Windows media or account data.

### M7 — service ownership and recovery

Registers service identity before VM creation, reserves inactive memory, owns
static DHCP identity and provides offline backup/restore transactions.

### M8 — Jellyfin reference appliance

Installs Jellyfin inside `svc-jellyfin`, exposes only the reviewed TCP/8096 path
while the VM is active and leaves future service slots inert.

### M9 — release evidence

Provides canonical Nitro/Predator plans, mode-`0600` evidence scaffolds,
ordered immutable gate records, storage and Ansible-recap probes, sensitive-data
refusal and deterministic final receipts. Raw logs remain local.

## Desktop and workstation phase

### M10 — domain manager and VM composition

Adds the `hyperlabctl` action registry, VM composer and GTK domain manager. The
manager resolves checked-in specs and lifecycle commands; it does not bypass
Ansible or execute destructive operations without the existing confirmations.

### M11 — desktop shell and Control Center

Unifies Waybar, the compact resident drawer, the full Control Center, Green /
Violet / Blue / Red palettes, public/personal wallpapers, keyboard switching,
Ly theming and native Swaybar fallback. The Nitro gate passed the real visual
checks and a second desktop apply with `changed=0`.

### M12 — snapshots, backups and golden images

Will add the missing snapshot/backup backend and the first reusable workstation
bases. Planned families are Arch, Fedora, Debian, CachyOS and the clean/dirty
Windows masters. Each base must support a clear permanent or disposable
lifecycle without changing the sealed golden image.

### M13 — seamless guest applications

Will add a Qubes-style application mode in which one program runs in a guest
but appears as an individual host window. Full desktop access remains available
through SPICE, SSH stays the management path, and VFIO/Looking Glass remain
separate display profiles. This milestone must not claim Qubes OS security
properties; it provides a similar workflow on the existing KVM architecture.

## Remaining release campaign

1. publish the exact green stage-1 and stage-2 trees on `main`;
2. bind the completed Nitro storage and desktop evidence to those commits;
3. run the remaining Nitro gates without broadening their claims;
4. repeat every affected gate after executable changes;
5. run Predator with the same stage-1/stage-2 commits that completed Nitro;
6. publish only sanitized evidence and final receipts in
   `arch-hypervisor-lab`;
7. build M12 workstation images only after the host repositories are coherent
   and published.

CI proves repository contracts. Hardware evidence proves physical compatibility.
