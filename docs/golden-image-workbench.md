# Golden Image Workbench

The Workbench turns a finished workstation guest into a Golden Image. The
decision and its reasons are in
[`adr/0015-golden-image-capture.md`](adr/0015-golden-image-capture.md); this
page is the operator's procedure.

```text
workbench-adopt   explicit: this domain is a Golden Image candidate
workbench-seal    shut off → flat copy → virt-sysprep → leftover scan → digest
image-prepare     the existing local import into the image store
image-validate    the existing receipt check
commit            images/<id>.yml with status sealed and its sha256
workbench-release the candidate and its staging leave the Workbench
```

The source domain is only read. It keeps working after the seal, and you can
keep using it.

## 1. Adopt

```bash
ansible-playbook -K playbooks/workbench-adopt.yml \
  -e workbench_domain=arch-dev-vfio -e workbench_profile=dev
hyperlabctl workbench list
```

The base image is read from `vm-specs/<domain>.yml`; a domain without a spec
names it with `-e workbench_base_image=<image>`. The image id defaults to
`<base>-<profile>-<date>`, for example `arch-dev-20261003`, and can be set with
`-e workbench_image_id=...`. An id that already has a manifest is refused: a
sealed image is never replaced.

## 2. Seal

Shut the domain down first, then:

```bash
ansible-playbook -K playbooks/workbench-seal.yml -e workbench_domain=arch-dev-vfio
```

The playbook installs `guestfs-tools` on the host, and:

1. refuses unless the domain is a candidate and shut off with exactly one
   file disk;
2. copies the disk, flattened, to `/var/lib/hyperlab-workbench/staging/<id>/`
   (root only);
3. generalizes the copy with `virt-sysprep`: every ordinary user account
   (UID 1000 to 59999) and its home directory, removed with the guest's own
   `userdel`, machine identity, SSH host keys, logs, shell histories,
   temporary files, the pacman cache, root's SSH, GnuPG, keyring,
   configuration, cache and npm directories, cloud-init instance state and the cloud-init sudoers file;
4. scans the copy read-only and refuses on any leftover of those;
5. checks and hashes it, writes `images/<id>.yml` into your checkout and
   prints the import command.

A refused or failed seal removes its staging; nothing reaches the store.

## 3. Import, validate, commit

Run the `image-prepare.yml` command the seal printed, then:

```bash
ansible-playbook -K playbooks/image-validate.yml -e image_factory_manifest=images/<id>.yml
```

Set `status: sealed` and the `sha256` that validation prints in
`images/<id>.yml`, review the whole manifest and commit it.

## 4. Release

```bash
ansible-playbook -K playbooks/workbench-release.yml -e workbench_domain=arch-dev-vfio
```

## Reserving an id for a Template

A Template can name an image before the image exists, as a draft. Its
manifest is then a **placeholder**: `status: not-built`, `sha256: null`,
`source_sha256: null`, `source_type: local`, and the reserved `id`. Adoption
accepts that id, and the seal replaces the placeholder with the captured
manifest. Any other manifest, sealed or not, is never replaced: adoption
refuses the id and the seal stops before copying.

## The second capture: `arch-dev-standard`

`workstation-dev-standard` is the development workstation without the
passed-through GPU. Its draft names `arch-dev-standard`, captured from
`arch-dev` (standard device, the same Workspace Shell on the emulated
display, `playbooks/guest-arch-dev.yml`):

```bash
ansible-playbook -K playbooks/vm-guest-inventory.yml -e guest_spec=vm-specs/arch-dev.yml
ansible-playbook -i inventory.ini -i /run/user/$UID/arch-dev.ini playbooks/guest-arch-dev.yml
ansible-playbook -K playbooks/vm-shutdown.yml -e guest_spec=vm-specs/arch-dev.yml
ansible-playbook -K playbooks/workbench-adopt.yml -e workbench_domain=arch-dev -e workbench_profile=dev -e workbench_image_id=arch-dev-standard
ansible-playbook -K playbooks/workbench-seal.yml -e workbench_domain=arch-dev
```

Then the import and validation commands the seal prints, `status: sealed`
and the digest in `images/arch-dev-standard.yml`, `status: ready` in
`templates/workstation-dev-standard.yml`, and the release.

## Deriving offline: `debian-server`

Some images only need packages added to a sealed upstream base, and the
base cannot be reached safely to install them: the Debian genericcloud image
has no QEMU Guest Agent, so its SSH host key cannot be pinned
([ADR 0026](adr/0026-offline-derived-images.md)). `images/debian-server.yml`
is a placeholder with a reviewed `derive` section (`base: debian`,
`install: [qemu-guest-agent]`). Nothing boots and nothing connects:

```bash
ansible-playbook -K playbooks/workbench-derive.yml -e workbench_image_id=debian-server
```

1. The base is checked: sealed in its manifest, a regular file in the store,
   and its SHA-256 equal to the sealed digest. It is copied to a flat qcow2
   in the root-only staging and never written.
2. `virt-customize --install qemu-guest-agent` runs apt inside the
   libguestfs appliance, with the appliance's own network. apt refuses any
   package whose signature does not verify against the Debian archive keys
   already inside the sealed base; nothing is trusted from the host.
3. `virt-sysprep` runs the default operations (logs, machine identity, SSH
   host keys, package caches) plus the Workbench's deletes, and for apt and
   dpkg removes `/var/cache/apt/archives/*.deb`, `/var/cache/apt/*.bin`,
   `/var/lib/apt/lists/*`, `/var/log/apt/*` and `/var/log/dpkg.log`; the
   machine-id is emptied last.
4. The read-only scan refuses every leftover it already knew and, in
   addition, any downloaded `.deb`, any apt log and `dpkg.log`.
5. The agent must be there and must start by itself: `qemu-ga` and
   `qemu-guest-agent.service` present, and either the systemd wants link the
   package creates or a udev rule that starts the unit when the agent's
   virtio port appears. Otherwise the derivation is refused and its staging
   removed. `image-validate.yml` checks the binary and unit again before the
   seal.
6. The staged image and its manifest replace the placeholder in the
   checkout; then the printed `image-prepare.yml` and `image-validate.yml`
   commands, `status: sealed` with the digest, and `server-debian` back to
   `ready`. `playbooks/workbench-discard.yml -e workbench_image_id=debian-server`
   removes the staging afterwards.

## What a Machine from this image looks like

No user, no home, no rice and no identity of the source: cloud-init creates
the account on first boot, and the profile playbook
(`guest-arch-dev-vfio.yml`, `guest-arch-gaming-clean.yml`,
`guest-arch-gaming-dirty.yml`) applies the rice. It is quick, because every
package is already in the image.

## Limits

The leftover scan checks known secret locations. A secret you stored in an
unusual system path is not detected; keep personal files in your home
directory, which never reaches the image.

The first sealed image, `arch-dev-20261003`, is published through the
`workstation-dev` Template; [`first-machine.md`](first-machine.md) creates a
Machine from it. The shell's Workbench section (phase 2) follows.
