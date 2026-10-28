# Changelog

This changelog covers the three repositories that make up HyperLab:
[`arch-bootstrap`](https://github.com/importriri/arch-bootstrap) installs the
encrypted Arch Linux host, this repository (`hyperlab-ansible`) turns it into
the virtualization workstation and owns image and Machine operations, and
[`arch-hypervisor-lab`](https://github.com/importriri/arch-hypervisor-lab)
holds the setup guide and the sanitized hardware evidence.

No version of HyperLab has been released. None of the three repositories
carries a tag, so everything below is unreleased work on their `main`
branches, and there is no earlier version to compare against. The planned
first release, v1, is described, with what still stands in its way, in the
[draft v1 release notes](docs/release-notes-v1.md).

Unless an entry says otherwise, it describes behaviour that is in the
source and checked by the repositories' own tests (software-verified). That
is not a hardware result: it does not mean the behaviour has been seen
working on a laptop. Where an entry mentions a laptop, the
observation keeps the date and scope the [roadmap](docs/roadmap.md) gives
it; most of them are the maintainer's own, unpublished observations, and
none is a replay of frozen release commits.

## Unreleased

### Installing the encrypted host

- `arch-bootstrap` installs Arch Linux on a LUKS2-encrypted Btrfs root with
  systemd-boot, the hardened kernel and zram instead of a swap partition. A
  second disk can be dedicated, encrypted, to virtual machine storage.
- A dry run is the default. A real run erases each disk you confirm by
  typing its full path again; the live medium cannot be selected.
  Confirming the right disk does not protect the others: the installer
  reaches its new partitions by their GPT labels (`ARCH_ESP`, `ARCH_ROOT`,
  `ARCH_VM`), and another attached disk that already carries one of those
  labels can be destroyed instead. Before a real run, disconnect disks you
  are not installing to, check the labels on every remaining disk and stop
  on any conflict; the
  [bootstrap threat model](https://github.com/importriri/arch-bootstrap/blob/main/docs/threat-model.md#partition-labels-are-global)
  gives the exact stop conditions. The dry run does not detect this hazard,
  and duplicate labels are not covered by tests.
- The installer finishes by writing a small storage hand-off file,
  `/etc/privatestack/bootstrap-storage.yml`, that says where virtual machine
  disks live. If that file cannot be written, the installation stops and
  reports failure instead of claiming success.
- Secure Boot keys are generated and files signed, but enrolling the keys in
  the firmware stays a manual step, and the initramfs is not signed.
- The path from `arch-bootstrap` to stage 2 has been exercised on the
  Nitro. A clean installation from frozen commits is still pending on both
  laptops.

### Handing the host over to stage 2

- Stage 2 accepts a virtual machine store only on an encrypted (dm-crypt)
  volume, in one of the two layouts the installer writes, with copy-on-write
  disabled. A store on a plain partition is refused.
- Host swap that is neither zram nor encrypted is refused, because guest
  memory swapped out by the host would land on it.
- The installer's storage file and stage 2's reader are compared by a test
  that runs the real writer, so a change on one side cannot pass silently.
- `playbooks/preflight.yml` identifies the laptop from its PCI IDs and
  refuses a computer it does not know. Two laptop profiles are reviewed,
  the Acer Nitro 5 with an RTX 3060 and the Acer Predator Helios 300 with an
  RTX 3070. A third profile, `no-gpu-passthrough`, is used only when you
  name it, and gives a host without GPU passthrough.
- `hyperlabctl doctor --hardware` checks a computer read-only before
  installation and proposes a profile to review.

### The host

- `playbooks/lab.yml` builds the host in one ordered run: KVM and libvirt,
  VFIO boot entries that reserve the NVIDIA GPU for virtual machines, five
  isolated networks (clean, dirty, dev, lab, services), the GPU hand-off
  policy, the image store, the Sway desktop on the integrated GPU and the
  host side of Looking Glass. A second run must report `changed=0`.
- Every pair of networks is blocked at the host, `lab` has no internet
  access, a guest can reach nothing on the host but DHCP and DNS on its own
  gateway, and each network has its own resolver.
- One GPU, one owner: several Machines may name the GPU, but only the
  running one holds it. Within one host boot the GPU may only move down the
  trust ladder clean → dev → dirty → lab; going back takes a host reboot.
- `playbooks/host-sleep-guard.yml`, outside `lab.yml`, keeps the host from
  suspending while a Machine holds the GPU.
- The preferred Hyprland session and the HyperLab shell (Machines, Control
  Center, Diagnostics, the Create view) are installed by a separate
  playbook, `playbooks/host-desktop-hyprland.yml`, outside `lab.yml`. It
  stages them without making Hyprland the default session; Sway stays the
  recovery session.

### Images, Templates and Machines

Nothing is adopted implicitly: a disk does not become an image, and a
virtual machine does not become a Machine, because it exists.

- Images are pinned by SHA-256 digest and checked again at every use.
  Official cloud images are downloaded and compared with the vendor's
  checksum file.
- The Workbench captures a shut-off virtual machine, removes every user
  account and home with `virt-sysprep`, scans for leftovers and seals the
  result as a read-only Golden Image.
- A Template pins one sealed image and limits the network, GPU use and
  resources a Machine may have. A Template that asks for more than its
  class allows is refused.
- `hyperlabctl machine create` records a Machine's intent, and `machine
  project` writes the virtual machine definition derived from it. The
  shell's Create view performs the same steps and runs the provisioning
  playbooks in one operation window, where the password prompts appear.
- Staged creation writes the Machine definition first and publishes the
  record last. If this intent stage is refused, its new files are removed
  when cleanup succeeds. Otherwise, the refusal says "cleanup incomplete"
  and names what stays. A process killed between the two writes can leave
  a definition that keeps the name taken. Failed provisioning retains the
  record, the definition and any libvirt domain already defined; see
  [ADR 0053](docs/adr/0053-withdraw-machine-intent.md) (proposed) for the
  cleanup and recovery limits.
- In the manual `create` and `project` path, `hyperlabctl machine withdraw`
  removes a record only when its bytes match the supplied SHA-256 digest,
  no generated definition matches the record's projection and no libvirt
  domain has that name. A stale, well-formed definition is kept; unreadable
  or unsafe inputs are refused.
- Server Machines (`server-arch`, `server-fedora`) are reached over SSH
  only. Their SSH host key is read through the QEMU guest agent and pinned,
  so the first connection never trusts a key offered on the network.
- After provisioning, the guest agent answers only the calls HyperLab uses;
  running commands through it is refused, and this is checked from the
  host.
- Disposable Machines lose everything they wrote when they stop. No
  disposable Machine has been tried on hardware yet.
- Every new Linux Machine starts in the host's time zone.

### The workstation inside a Machine

- The `arch-dev-vfio` workstation runs with the NVIDIA GPU passed through
  and is shown on the host through Looking Glass. The maintainer saw it,
  with its shell, on the Nitro on 2026-10-03 (unpublished); pre-login
  display recovery, input isolation and physical audio are still open. The
  Linux Looking Glass sender is built from a pinned source and stays
  experimental.
- The Guest Workspace Shell gives each workstation Desks, projects that
  reopen their applications, a launcher, an overview, a key sheet
  (`ALT+H`), per-Desk quiet mode and optional local time tracking. If the
  shell fails, Waybar takes over and every key keeps working.
- The host, never the guest, decides which Machine and network a window
  belongs to, and shows it with a frame colour, also around fullscreen
  guests.
- Copying from the host to one chosen Machine is an explicit action,
  `SUPER + SHIFT + V`; there is no shared clipboard. `SUPER + F1` shows
  every host key.
- No guest gets the SPICE agent channel, USB redirection, file transfer or a
  microphone. Display servers listen only on a local socket or loopback.

### Refusals that were corrected

These defects let something through that should have been refused. Each is
fixed in source, with a test that fails on the old behaviour.

- The Debian cloud image was declared to carry the QEMU guest agent and did
  not. Image validation now looks inside the image, read-only, and refuses
  a false claim; see
  [the write-up](problems/sealed-image-claimed-guest-agent.md).
- A failed write of the GPU ladder state let a dirtier workload leave the
  ladder at a cleaner level. The state is now written under a lock, and a
  failed write refuses the start.
- A release gate could be recorded as passed with its yes/no evidence
  false. A pass now needs every such value true.
- The emergency-stop Restore forgot a paused Machine whose state it could
  not read, and a failed key-vault dialog could count as consent. Both now
  fail closed.
- A Machine definition edited by hand, replaced by a link or unreadable,
  and a provisioning plan naming a playbook that is not the reviewed file,
  are refused before the first step runs.
- The diagnostics archive could keep fragments of secrets; complete values
  are now redacted before anything is cut short.
- A FAT boot partition mounted so that other users could write its
  directories is refused before boot entries are changed.
- The showcase demo script printed the host name, user name and addresses
  on the recorded terminal; it now prints only a generic checklist.

### Documentation and project files

- A [threat model](docs/threat-model.md) says what HyperLab protects
  against and what it does not, and [SECURITY.md](SECURITY.md) explains
  private vulnerability reporting.
- [CONTRIBUTING.md](CONTRIBUTING.md) explains how to run the checks and
  what evidence a change needs.
- [Third-party licences](docs/third-party-licences.md) records the origin of
  every tracked file and the licences of what the playbooks install, and
  lists the items whose provenance or permission is still unresolved.
- `arch-hypervisor-lab` has a
  [setup guide](https://github.com/importriri/arch-hypervisor-lab/blob/main/SETUP.md)
  from the Arch Linux live prompt to the lab, with the points where the
  current route stops.

### Compatibility

- Installed state still uses `/etc/privatestack`, `/var/lib/privatestack`
  and `privatestack-*` helper names. They are kept on purpose; no migration
  to new names exists.
- `server-debian` is a draft again and is not offered when creating a
  Machine. It waits for a Debian image that carries the QEMU guest agent.
  A Debian base sealed before this correction fails validation until its
  receipt is re-issued with `playbooks/image-rereceipt.yml`.
- Once a workstation Machine's first provisioning has finished, later
  profile runs ask for that Machine account's password.
- A disposable Machine boots as new each time, with new SSH host keys: run
  the inventory step again after each start to pin the new key.
- Release evidence uses acceptance schema v2. Plans made with the earlier
  schema are rehearsal data and must be recreated.

### Known limitations

v1 is not ready. The [draft release notes](docs/release-notes-v1.md) list
what is missing and what must happen before a release; the main points:

- neither laptop has passed the complete pipeline on frozen commits;
- no project installer ISO exists;
- the Hyprland session and Create view are not part of `lab.yml`, and no
  Machine has been created from the Create view on hardware;
- `server-debian` is a draft, and neither the Debian nor the Fedora server
  has been reached over SSH on hardware;
- the per-run GPU lease is a proposal and is not built;
- disposable Machines do not restore their closed guest agent or re-pin
  their host key after a restart;
- QEMU processes are not yet confined by AppArmor or separated per Machine.
