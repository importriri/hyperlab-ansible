# ADR 0010 - A sealed image is a base plus a provenance receipt

## Context

The guest lifecycle previously trusted two checked-in fields: `status: sealed`
and an artefact SHA-256. Those fields identify bytes, but do not prove how the
bytes reached the managed image store, whether `qemu-img check` passed, whether
the virtual size matches policy, or whether a private Windows workshop path was
accidentally recorded.

Acquisition also has two fundamentally different trust boundaries:

- redistributable Linux cloud images may be downloaded from a pinned HTTPS URL;
- Windows masters and other private artefacts must be imported from a local
  workshop output that never enters Git and whose host-local path must not
  survive in persistent metadata.

A concurrent or interrupted acquisition must not overwrite an existing base or
let one process delete files owned by another.

## Decision

M5 adds an `image_factory` brick between `image_store` and `guest`.

`tools/image_plan.py` converts one checked-in manifest plus explicit acquisition
evidence into a deterministic plan. Automatic acquisition is restricted to
redistributable `official-cloud` images over credential-free HTTPS. `local`
imports require an absolute path outside the managed store and an independently
supplied SHA-256. `official-iso` remains workshop input and cannot be sealed
directly; its installed qcow2 output is imported as `local`.

The immutable policy hash includes effective source URL and source checksum,
even when they are supplied as temporary overrides. It excludes only seal
evidence that necessarily changes after preparation: manifest status, final
artefact checksum and observed Looking Glass build. Therefore the policy hash
is stable when the reviewed evidence is later committed to the manifest.

Preparation performs every read-only gate before a managed write:

1. validate repository schemas and the selected manifest path;
2. validate the M2 store identity and runtime QEMU identity;
3. validate local source type/checksum when applicable;
4. require conservative free space;
5. acquire a per-image directory lock;
6. re-read every transaction path while holding the lock;
7. download or copy only into a staging path;
8. verify source checksum, qcow2 format, exact virtual size, independence and
   `qemu-img check`;
9. atomically commit the read-only base;
10. atomically commit a root-owned provenance receipt;
11. re-read and validate the complete transaction before success.

Rollback exists only inside the block that owns the lock and newly-created
files. Failure to acquire the lock cannot enter rollback. A second process that
observed an empty store but acquires the lock after another process completed
must re-read the paths and refuse rather than overwrite.

The receipt records the immutable policy hash, base path, artefact checksum,
source type, source checksum, safe source basename, qcow2 evidence and optional
Looking Glass build. A private local receipt records neither the local source
path nor a source URL.

Preparation does not edit Git. When a prepared transaction is valid, it prints
the exact manifest evidence to commit. After that commit is pulled,
`image-validate.yml` requires `status: sealed`, the matching artefact checksum,
source checksum and optional Looking Glass evidence.

The guest role rebuilds the M5 image plan in `validate` mode and verifies the
base against its receipt before package installation, disk creation, locks or
libvirt writes. A manifest claiming `sealed` without a valid receipt is not a
usable image.

## Consequences

- An image is usable only when manifest, immutable policy, base bytes and
  receipt all agree.
- Private Windows paths never enter Git or persistent receipts.
- Source URLs and checksums can be supplied during the final campaign and then
  committed without changing the receipt policy hash.
- Existing bases are never replaced in place; operators must explicitly remove
  a complete transaction before rebuilding it.
- Guest creation now depends on the `image_factory` brick and independently
  verifies the selected image, so a global brick stamp cannot authorize a
  different or corrupted base.
- Actual downloads and Windows imports remain part of the deferred hardware
  campaign; CI exercises synthetic policies, files, receipts and qemu-img
  responses only.
