# ADR 0028 - Build provenance in a Workbench image's manifest

Status: accepted. Implements the milestone 3 item "build commits and the
package list in the image manifest".

## Context

A Golden Image the Workbench stages carries a digest and a receipt that
binds its manifest policy ([ADR 0010](0010-image-provenance-transaction.md),
[ADR 0024](0024-rereceipt-after-policy-change.md)). Neither says what the
image was built from or what it contains: two versions of `arch-dev` differ
by digest, and nothing in the repository says how.

The Workbench knows three things without trusting the guest: the checkout it
runs from, the base image it started over, and the image's files, readable
offline.

## Decision

The Workbench writes a `build` section into every manifest it stages,
captured or derived:

- `workbench_commit`: the checkout's `HEAD`, and `workbench_tree_dirty`:
  whether tracked files differed from it. Untracked files are not counted.
  For a capture this is the commit that sealed the image, not necessarily
  the one whose profile playbook built the rice; for a derivation it is the
  commit that built it;
- `base_image` and `base_sha256`: the base the image was built over and its
  digest as its manifest records it (`null` when the base manifest records
  none);
- `packages`: the package manager, the count, the file and its sha256. The
  list is read from the generalized copy by libguestfs inspection
  (`virt-inspector`), never by booting it, and written as sorted `name
  version` lines to `images/packages/<id>.txt`.

Text that comes out of the image is kept only in a narrow form: a package
line that does not match `name version` with ordinary characters refuses the
seal. The checkout is read with `git --no-optional-locks`, so the Workbench,
running as root, never rewrites the operator's index.

`tests/schema_validate.py` refuses a manifest whose package list is missing,
no longer matches its digest or count, or is not sorted, and a
`base_sha256` that is not the base's digest.

## Consequences

- Comparing two versions of an image is a diff of two package lists in the
  repository, and the manifest says which commit sealed each.
- `build` is part of the manifest policy, so a receipt binds it.
- Images sealed before this decision (`arch-dev-20261003`) have no `build`
  section; they are not rewritten.
- A commit recorded as dirty is still accepted: the record says so instead
  of refusing an operator's local test.
