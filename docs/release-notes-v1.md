# HyperLab v1 release notes

> **Draft — v1, unreleased and unqualified.** No v1 release exists. No
> version has been tagged or published, no laptop has passed the complete
> pipeline, and nothing here is a compatibility claim. These notes describe
> what v1 is meant to be, what can be installed today and what still has to
> happen first. The [changelog](../CHANGELOG.md) lists the changes
> themselves.

## Who HyperLab is for

HyperLab turns one laptop running Arch Linux into a virtualization
workstation. Work runs in separate virtual machines, called Machines, each
placed by the host in one trust network: `clean` for trusted accounts and
store games, `dev` for development, `dirty` for untrusted software, `lab`
for offline research and `services` for appliances. The laptop's NVIDIA GPU
is passed through to one running Machine at a time, and its picture comes
back to the host desktop through Looking Glass.

It is meant for one person who owns the laptop, is at ease with Arch Linux,
the command line, disk encryption and firmware settings, and wants that
separation without giving up GPU acceleration. It is not meant for a
computer whose disks must be kept, a dual-boot system, a shared or
multi-user computer, or anyone who needs the guarantees of Qubes OS (see
[Security and data warnings](#security-and-data-warnings)).

## What you need

- An x86_64 computer that boots in 64-bit UEFI mode, with hardware
  virtualization enabled in the firmware.
- One whole disk you are prepared to erase, and optionally a second one
  for Machine storage. Both are erased.
- A verified external backup of everything you want to keep, and a
  separate device to read the guide on.
- Internet access during installation, and your own SSH key for the
  Machines.
- For GPU passthrough: IOMMU and interrupt remapping enabled, an integrated
  GPU that keeps driving the laptop's display, and an NVIDIA GPU whose PCI
  functions match a reviewed profile.
- Enough memory and disk for the Machines you plan to run. The first
  workstation image needs a 100 GiB disk and 4 GiB of memory per Machine;
  the [setup guide](https://github.com/importriri/arch-hypervisor-lab/blob/main/SETUP.md)
  explains how to budget the rest.

Two laptop profiles are reviewed: `nitro-3060` (Acer Nitro 5, RTX 3060
Mobile) and `predator-3070` (Acer Predator Helios 300, RTX 3070 Mobile).
The preflight identifies them from their PCI IDs and refuses any other
computer. A third profile, `no-gpu-passthrough`, is used only when you name
it: it gives the host without GPU passthrough, and is no claim that a
desktop with a passed-through GPU works on that computer. A laptop is not
supported because its GPU has the same marketing name as a reviewed one.

## The three repositories

| Repository | Role |
| --- | --- |
| [`arch-bootstrap`](https://github.com/importriri/arch-bootstrap) | Installs the encrypted Arch Linux host from the live medium and writes the storage hand-off file. |
| `hyperlab-ansible` (this repository) | Turns that host into the virtualization workstation and owns every image, Template and Machine operation. |
| [`arch-hypervisor-lab`](https://github.com/importriri/arch-hypervisor-lab) | Holds the setup guide, troubleshooting, the hardware compatibility record and sanitized evidence. |

None of them certifies another. A green CI run in any of them is a software
result, not a hardware one.

## Where to start

Follow the setup guide in `arch-hypervisor-lab`,
[`SETUP.md`](https://github.com/importriri/arch-hypervisor-lab/blob/main/SETUP.md).
It goes from an authenticated upstream Arch Linux live medium through
`arch-bootstrap` and stage 2, and marks the places where the current route
stops. Its
[troubleshooting page](https://github.com/importriri/arch-hypervisor-lab/blob/main/TROUBLESHOOTING.md)
starts from symptoms, and its
[FAQ](https://github.com/importriri/arch-hypervisor-lab/blob/main/FAQ.md)
answers the common questions about hardware, erasure and security.

## What can be installed today

This is a development route, not a release. It is what the setup guide
walks through:

1. Boot the upstream Arch Linux installation medium, after verifying its
   signature, and run `arch-bootstrap`. A dry run is the default; a real run
   erases each disk you confirm.
2. After the first boots, clone this repository and run
   `playbooks/preflight.yml`, then `playbooks/lab.yml` twice. The second run
   must report `changed=0`. This builds KVM and libvirt, the GPU
   reservation, the five networks and their isolation, the image store, the
   Sway desktop and the host side of Looking Glass.
3. Prepare the official Arch, Fedora and Debian cloud images, each checked
   against the vendor's checksum and pinned by digest.
4. Create server Machines from the `server-arch` and `server-fedora`
   Templates with `hyperlabctl`, as
   [the first Machine guide](first-machine.md) shows.

What this route does not give you:

- **The preferred desktop.** Hyprland is the preferred host session and
  Sway the recovery one, but `lab.yml` installs Sway. The Hyprland session
  and the HyperLab shell, where the Create view lives, come from a separate
  playbook that stages them without making them the default. No single host
  playbook for v1 has been accepted yet; assembling the parts by hand does
  not make a v1 host.
- **The workstation image.** The `workstation-dev` Template pins
  `arch-dev-20261003`, a private image captured on the maintainer's laptop.
  It is not redistributable and cannot be downloaded; on any other
  computer that Template has no image to use. The
  [Workbench](golden-image-workbench.md) can capture and seal your own
  workstation image, but a Template pinned to it is your own change.
- **Debian servers.** `server-debian` is a draft: the upstream Debian cloud
  image has no QEMU guest agent, which HyperLab needs to pin a new
  Machine's SSH host key. It waits for `debian-server`, the Debian image captured through the
  Workbench with the agent, which has not been built.

## The ISO

The intended main way to install v1 is a project installer ISO. It does not
exist. Its design is a
[proposal in `arch-bootstrap`](https://github.com/importriri/arch-bootstrap/blob/main/docs/adr/0001-iso-build-and-distribution.md)
that has not been accepted; no profile, build, image, signature or download
exists. Until one does, the upstream Arch Linux medium with `arch-bootstrap`
and Ansible is the only route, and it is a development and preparation
route, not a released installer.

## What v1 is meant to include, and where each part stands

v1 keeps the parts listed in
[the roadmap's v1 scope](roadmap.md#v1-scope-and-evidence-status). None of
them is accepted on hardware as part of a frozen release.

| Part | Where it stands |
| --- | --- |
| Reference workstation (`arch-dev-vfio`) | Repeated runs of its playbook with `changed=0` and the Guest Workspace Shell seen by the maintainer on the Nitro on 2026-10-03, unpublished. Pre-login display recovery, input isolation and the physical audio check are open. |
| SSH server Templates | `server-fedora` is ready on the sealed Fedora 44 image; `server-debian` is a draft. Neither has been reached over SSH on hardware. (An Arch server, `srv-01`, was, as the maintainer observed without publishing it, but `server-arch` is not one of the two v1 server Templates.) |
| Plan and Intent | Software-verified on `main`: the creation plan reports what a Template allows, and one staged creation publishes a Machine record only after its definition is written. A refused creation leaves nothing behind. The decisions behind it, [ADR 0017](adr/0017-shell-machine-creation.md) and [ADR 0053](adr/0053-withdraw-machine-intent.md), are still proposals. |
| Create view | Built in the shell and software-verified offscreen. No Machine has been created from the shell on hardware. |
| Provisioning | The runner and its checks are software-verified against inert test playbooks, within the limits [ADR 0017](adr/0017-shell-machine-creation.md) lists. A real provisioning run from the shell has not been observed. |
| Disposable Machines | The disk that discards every write at stop is software-verified. Closing the guest agent again and re-pinning the SSH host key after each later start are not built ([ADR 0018](adr/0018-disposable-discards-on-stop.md)). No disposable Machine has been tried on hardware. |
| GPU lease | Part of v1. A Machine that holds the GPU only for one run is a proposal, [ADR 0019](adr/0019-gpu-lease.md), not decided and not built. What it builds on, one GPU shared by several definitions and the trust ladder, is software-verified. |
| Showcase | Part of v1. The storyboard and a read-only demo script exist ([showcase](showcase.md)); the lease shot waits for the lease, and the recording and its privacy review have not been done. |
| Release qualification | The checked-in release gate order (`release/acceptance.v2.yml`) predates the v1 scope and has no gate for a Machine created from the shell, the disposable discard, the two SSH servers, the GPU lease or the Showcase. A v1 order to replace it is not decided. |

The old gate order also contains Jellyfin service and recovery gates. That
does not add Jellyfin, or any later roadmap work, to the v1 scope; whether
those gates stay is part of the undecided v1 order.

## Known blockers

- No frozen pair of `arch-bootstrap` and `hyperlab-ansible` commits, and no
  accepted v1 release manifest.
- Both full pipelines are pending: the
  [compatibility record](https://github.com/importriri/arch-hypervisor-lab/blob/main/hardware/compatibility.yml)
  marks the Nitro and the Predator `pipeline-pending`. Their earlier results
  are single components, not a reproducible installation.
- The Hyprland session and the Create view are outside `lab.yml`, so the
  host v1 demonstrates is not the host whose second run is checked for
  `changed=0`.
- `server-debian` is a draft, and neither v1 server Template has an SSH
  observation on hardware.
- Provisioning from the shell has not run for real; disposable Machines do
  not close their guest agent or re-pin their host key after a restart.
- The GPU lease is not built, and the Showcase cannot be recorded in full
  without it.
- The host labels a window it cannot attribute to a Machine, an ordinary
  terminal for example, as the host's own
  ([shell boundaries](hyperlab-shell.md)).
- The GPU hook refuses a domain HyperLab does not manage that passes a PCI
  device through only when the domain definition uses the usual PCI device
  entries; a domain defined by hand with raw QEMU arguments is outside that
  check.
- The provenance or permission of 105 tracked images, and of some files
  in the pinned upstream sources HyperLab builds, is unresolved
  ([third-party licences](third-party-licences.md)).

## Security and data warnings

- **The installer erases disks.** A real `arch-bootstrap` run erases every
  disk you confirm, including other operating systems and their boot
  entries. There is no rollback and no dual boot.
- **Back up first, and keep backing up.** Machine snapshots and Machine
  backups are not built. Only offline service backup and restore
  playbooks exist, and their hardware campaign is incomplete. No general
  migration or restore path for a host or its Machines has been proven, and
  no migration away from the `/etc/privatestack` names exists.
- **HyperLab does not provide Qubes OS security properties.** The host
  kernel, KVM, QEMU and the host session are all trusted. Read the
  [threat model](threat-model.md) before relying on any separation.
- **Your desktop session controls every Machine.** Your account is in the
  `libvirt` group, which gives full control of every Machine without a
  password prompt. Anything running in your host session has that power;
  the password prompts of the operation window do not limit it.
- **QEMU processes are not yet confined.** Every Machine's QEMU runs as the
  same user, so an escape from one could reach every Machine's disk
  ([write-up](../problems/qemu-processes-share-one-identity.md)). The
  AppArmor profile is built and starts in complain mode; per-Machine
  identities are built and off. Neither is enforced or proven on hardware.
- **Screen and input are not accepted yet.** Keyboard and pointer isolation
  in Looking Glass, the frame around fullscreen guests and the pre-login
  path have not been accepted on hardware
  ([write-up](../problems/looking-glass-input-isolation.md)). There is no
  real audio check yet either.
- **A digest or a green CI run is not runtime acceptance.** A pinned image
  digest says which bytes were sealed, not that a Machine made from them
  works; a CI run says the source passes its checks, not that a laptop
  does.
- **No signed ISO, no frozen replay.** Nothing in the code or in earlier
  notes implies a signed installer image, an audio result or a replay of
  frozen commits on either laptop.
- **Keep raw evidence private.** If you report a problem, follow
  [SECURITY.md](../SECURITY.md) for anything security-related, and do not
  publish raw logs, screenshots, addresses, keys or image contents.

## Source revisions read for this draft

These are the `main` revisions read on 2026-10-28 to write this draft. They
are inspection inputs only: they are not a frozen release pair and no
hardware campaign has run on them.

| Repository | Revision read |
| --- | --- |
| `hyperlab-ansible` | `26b0535b45635b635727483e7d96f90406750f6a` |
| `arch-bootstrap` | `a44afa947cd3b0f2bf7522ff7f12897c37e3a417` |
| `arch-hypervisor-lab` | `2b32a56777d4a1976b61a4520645b716c5f191b0` |

A release names its own pair of `arch-bootstrap` and `hyperlab-ansible`
commits, frozen before the hardware campaign, as
[release evidence](release-evidence.md) describes. The evidence repository's
revision is recorded separately and is not part of that pair.

## Before this draft can become release notes

Each of these must exist first; none does today.

1. **Accepted software and manifest.** The v1 blockers above fixed on
   `main`, and an accepted v1 release manifest whose gates cover the v1
   scope.
2. **The final automation pair.** Exact `arch-bootstrap` and
   `hyperlab-ansible` commits, frozen for the campaign.
3. **The Nitro campaign.** Every required gate passed on the Nitro against
   that pair, sealed, with sanitized evidence published in
   `arch-hypervisor-lab`.
4. **The Predator replay.** The same pair replayed on the Predator, with its
   own results published separately. A change needed for the Predator makes
   a new pair and reopens the Nitro.
5. **Rights and reporting.** Licence, authorship and the unresolved
   provenance items reviewed for publication, and private vulnerability
   reporting enabled and confirmed in each repository's settings; a policy
   file alone does not enable it.
6. **The ISO, if v1 ships one.** An accepted design, a build whose two
   independent runs are compared, a boot on both laptops, and a signature
   with a published key fingerprint that users can check.
7. **The Showcase.** The real recording, and its privacy review frame by
   frame, as [the showcase](showcase.md) describes.
8. **The release decision.** The maintainer decides whether and when to
   release. Until then this page stays a draft.
