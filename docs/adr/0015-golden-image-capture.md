# ADR 0015 - A Golden Image is captured from an adopted, generalized workstation

## Context

The product chain is Image Factory → sealed Golden Image → Template → Machine
([`../c10-machine-factory-contract.md`](../c10-machine-factory-contract.md)).
Upstream cloud images enter that chain through `image_factory`
([`0010-image-provenance-transaction.md`](0010-image-provenance-transaction.md)),
but a finished workstation guest cannot: a riced, provisioned `arch-dev-vfio`
proves a recipe, and there is no reviewed way to turn its disk into a reusable
image.

Since Machines became product-only, existing domains such as `arch-dev-vfio`
are visible only in Diagnostics. The operator lost a place to keep preparing
them, and nothing records which domain is meant to become an image.

A workstation disk is also the most personal artefact on the host: SSH keys,
shell history, browser profiles, keyrings, tokens, machine identity and
whatever the operator left in their home directory. An image made from it is
copied into every Machine created from it.

## Decision

### Workbench

The Workbench is an explicit, host-owned list of Golden Image candidates.

- A domain enters it only through `playbooks/workbench-adopt.yml`, run by the
  operator with become. Existing does not mean adopted: nothing is added
  automatically, in line with the C10 rule that a domain never becomes a
  product object because it exists.
- The record lives in `/var/lib/hyperlab-workbench/registry/<domain>.json`,
  root-owned, written atomically by `tools/workbench.py`. It names the domain,
  the intended image id, the rice profile, who adopted it and when, and its
  state: `candidate`, then `captured`.
- A Workbench entry is never a Machine. It carries no trust, provenance or GPU
  claim and is not counted by the product inventory.
- `hyperlabctl workbench list` reads the registry without privilege; the shell
  shows it in its own Workbench section.

### Capture, generalization and seal

`playbooks/workbench-seal.yml` turns a `candidate` into a sealed-to-be image in
one transaction under a lock:

1. refuse unless the domain is adopted and **shut off**;
2. copy its single disk, flattened, to
   `/var/lib/hyperlab-workbench/staging/<image>/` (root, 0700). The source
   disk is only read; the domain keeps working exactly as before;
3. generalize the copy offline with `virt-sysprep`: machine identity, SSH host
   keys, logs, shell histories, temporary files, package caches, cloud-init
   instance state, and **every ordinary user account with its home
   directory**, removed by the guest's own `userdel` inside the copy. The
   rice is not carried in a home directory; it is reapplied to the new user
   of each Machine by that Machine's profile playbook;
4. scan the generalized copy and refuse on any leftover: a home directory,
   root's SSH, configuration, cache or npm directory, an SSH host key, a non-empty machine-id, a shell
   history, a keyring, a GnuPG or SSH directory, a cloud-init instance or a
   sudoers file naming a removed user;
5. check the image, hash it, and write a manifest `images/<image>.yml` into the
   operator's checkout with `source_type: local`, `generalized: true`,
   `contains_personal_data: false`, `private: true` and the digest as
   `source_sha256`;
6. mark the entry `captured`.

The staged disk then enters the store through the existing `image_factory`
local import, unchanged: `image-prepare.yml` with the staged path and digest,
then `image-validate.yml`. The operator reviews and commits the manifest as
for every other image. `workbench-release.yml` removes the entry and its
staging directory.

A sealed image is immutable. Capturing the same workstation again produces a
new image id, so a Template pinned to an earlier digest never changes under a
Machine.

## Consequences

- `guestfs-tools` becomes a host dependency of the Workbench playbooks.
- Generalization happens on a copy and offline: a failed or refused seal
  leaves the workstation untouched and nothing in the store.
- Machines created from a captured image start without a user and without the
  rice; cloud-init creates the account and the profile playbook applies the
  rice, quickly, because every package is already in the image.
- The scan is a deny list of known secret locations, not a proof that no
  secret remains. A file the operator stored in an unusual system path is not
  detected; the ADR keeps home directories out entirely so the common case
  never reaches the image.
- Phase 2 adds the Workbench section to the shell; phase 3 publishes the first
  Template, `workstation-dev`, pinned to a captured digest.
