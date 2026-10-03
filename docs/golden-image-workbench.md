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
3. generalizes the copy with `virt-sysprep`: every user account and home
   directory, machine identity, SSH host keys, logs, shell histories,
   temporary files, the pacman cache, root's SSH, GnuPG and keyring
   directories, cloud-init instance state and the cloud-init sudoers file;
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

The shell's Workbench section (phase 2) and the first Template,
`workstation-dev`, pinned to a sealed image (phase 3) follow.
