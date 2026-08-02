# ADR 0001: Hyperlab image-store layout

- Status: accepted for M2 static integration
- Scope: directory layout and validation only

## Context

Guest images, overlays, firmware variables, cloud-init media and TPM state have
different lifecycles. Putting them in one undifferentiated directory makes
cleanup, cloning and access control depend on filename conventions. The layout
must exist before the first image is imported; otherwise the first image
silently becomes the layout decision.

M2 therefore creates an empty, validated storage tree. It does not create or
convert images, define domains, change mounts/subvolumes, or apply filesystem
attributes.

## Decision

The shared root is:

```yaml
hyperlab_root: /var/lib/libvirt/images/hyperlab
```

The required tree is:

```text
hyperlab/
├── bases/
│   ├── windows/
│   └── linux/
├── disposable/
├── permanent/
├── cloud-init/
├── nvram/
├── tpm/
├── snapshots/
├── exports/
├── cache/
└── state/
```

`group_vars/all/storage.yml` defines the required path set independently from
the role defaults. A runtime override cannot remove a directory and redefine
the contract it is checked against.

## Access model

Three access classes are explicit in `image_store_layout`:

- `admin`: owned by the administrator group;
- `qemu`: group-owned by the effective QEMU runtime group;
- `swtpm`: group-owned by the effective swtpm runtime group.

QEMU and swtpm are separate processes and may use different identities. TPM
state is therefore not assigned to the QEMU group. `tpm/` is `0750` for the
swtpm group: the state remains unavailable to unrelated users while the
emulator can traverse its own namespace. Per-VM TPM directories and files must
still be created with narrower ownership/modes by the later guest lifecycle
brick.

The root is `0751` so non-root runtime identities can reach their assigned
subtrees. `bases/` and its children are `0555`: ordinary non-root writes fail,
while backing files remain reachable. This is accidental-write protection, not
immutability. Root is not constrained by Unix mode bits, and directory modes do
not make files immutable.

No recursive ownership or mode operation is permitted. Every directory is
managed individually so an existing image is never rewritten as a side effect
of reapplying the layout.

## Runtime identity gate

`/etc/libvirt/qemu.conf` is read for explicit `user`, `group`, `swtpm_user` and
`swtpm_group` settings. Commented examples are not treated as defaults:
libvirt vendors can choose QEMU identities at build time, and assuming
`root:root` would turn an unknown hardware fact into a plausible but unsafe
configuration.

When any value is not explicitly configured, the corresponding
`hyperlab_*_declared` host value must replace the
`__REQUIRED_FROM_HARDWARE__` sentinel. The role refuses before creating a
directory while any sentinel remains. It then verifies every administrator,
QEMU and swtpm user/group through `getent`.

For the reviewed Arch hypervisors, `host_vars/localhost.yml` records the Nitro
observation and package contract as QEMU `libvirt-qemu:libvirt-qemu` and swtpm
`tss:tss`. The shared variables deliberately retain their sentinels so a new
inventory cannot inherit those host facts accidentally. `kvm_host` installs
`swtpm` before `image_store`, ensuring the `tss` account exists at the point
where the identity gate runs. An explicit setting in `qemu.conf` still wins and
must pass the same account and traversal checks.

After creation, each non-root runtime user executes `/usr/bin/test -x` against
every directory assigned to its access class. This proves the complete path,
including parent directories and supplementary-group membership, is actually
traversable. Merely finding a group in `getent` is not sufficient.

## Path and mount safety

Before writing, the role refuses:

- non-string, relative, ambiguous or protected roots;
- `..`, duplicate separators and trailing separators;
- a canonical path different from the declared path, including symlinked
  ancestors;
- a root/component that is a symlink, regular file or other non-directory;
- a non-list layout, non-mapping elements, missing fields, duplicate paths,
  absolute components, invalid access classes or unquoted/invalid modes;
- a layout missing any independently required directory;
- a pre-existing component whose `st_dev` differs from the root.

After creation, every component is read again with `follow: false`. The role
verifies directory type, absence of symlinks, device ID, owner, group and mode.
The post-check also catches a mount introduced between the pre-check and the
write.

These checks are not atomic filesystem locks. A privileged concurrent actor can
still race tasks. The post-condition narrows and changes the race window; it
does not eliminate TOCTOU.

## Capacity

The value `image_store_capacity_plan_gib` is derived from the largest declared
image plus overlay headroom. At M2 it is a warning, not a precondition: M2
creates empty directories and a small manifest. The later import brick must
re-measure and refuse immediately before consuming space.

On Btrfs, `size_available` is only a planning signal because allocation,
metadata and compression make statvfs an imperfect predictor.

## Btrfs NOCOW

The bootstrap is expected to create the image subvolume and apply `chattr +C`
while it is empty. M2 reads the attribute with `lsattr`; it never changes it.
Applying `+C` after files exist does not convert those files.

On Btrfs, NOCOW verification is strict by default. Before the first write, the
role finds the nearest existing ancestor of the declared root and verifies that
new directories can inherit `+C` from it. After a real creation pass it reads
the created root again and proves that inheritance actually occurred. Attribute
parsing inspects only the first `lsattr` field, never the path text. A relocation
is therefore not merely a variable edit: the new target must also have the
intended mount, NOCOW inheritance, capacity and runtime traversal.

`readlink` is provided by coreutils and `lsattr` by e2fsprogs; both are expected
on the Arch host. Their use is read-only and explicitly allowlisted by the
structural contract. No shell task is permitted.

## Check mode and verification boundary

Check mode runs every pre-write refusal, including identity, canonical path,
mount and NOCOW-inheritance checks, and predicts each directory change. It does
not pretend an absent directory was created: final type/device/owner/group/mode,
runtime traversal, created-root NOCOW and manifest contents are deferred to the
real pass. This avoids both false failures and false claims about a filesystem
state that check mode cannot create.

CI proves data shape, task ordering, read-only validation, exact command
allowlisting, refusal cases, identity sentinels, NOCOW parsing, check-mode guards
and preservation of M1 contracts. CI does not prove the Nitro's compiled libvirt
identities, Btrfs attribute, mount topology, free-space report or Ansible changed
count. Those remain hardware gates.

## Consequences

- An empty store is a valid M2 result.
- Image and VM lifecycle remain outside this brick.
- QEMU and swtpm permissions are independently reviewable.
- The role may stop before writing until host identities are observed.
- A second real run is required to demonstrate `changed=0`; static reasoning is
  not called hardware idempotence.
