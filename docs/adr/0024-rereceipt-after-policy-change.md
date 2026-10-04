# ADR 0024 - Re-issue a receipt after a policy change only for an unchanged vendor download

## Context

[ADR 0010](0010-image-provenance-transaction.md) gives every sealed base a
provenance receipt. The receipt binds `policy_sha256`, the digest of the
whole manifest except `status`, `sha256` and the observed Looking Glass
build, so a base cannot quietly be used under a policy it was not prepared
for. When a policy field is wrong, as `supports.qemu_guest_agent` was for
the Debian 13 genericcloud image, correcting it makes the sealed base fail
validation, and no procedure existed to recover except removing the base and
receipt by hand and importing again.

For an official cloud image the factory keeps no separate cache: the
verified download is moved into the store and becomes the base, byte for
byte. The base is the source.

## Decision

A re-receipt is a separate, explicit factory operation,
`playbooks/image-rereceipt.yml`:

- it needs `-e image_factory_confirm_rereceipt=<image id>`;
- it accepts only a sealed `official-cloud` image whose recorded digest
  equals its pinned `source_sha256`, that is, a base that is the vendor's
  download; Workbench and workshop images are imported again instead;
- under the per-image lock it inspects the base (format, virtual size,
  SHA-256 against the pin), fetches the vendor's checksum file again and
  checks the base against it with the vendor's own algorithm (SHA-256 or
  SHA-512, GNU or BSD format), and refuses on any difference or ambiguity;
- only then does it render a new receipt for the current policy and replace
  the old one atomically, and it validates the image against it, which
  includes the guest agent check;
- the base is only read: never moved, replaced or deleted.

## Consequences

- Correcting a manifest is a reviewed commit followed by one confirmed
  command, not a hand-edited store.
- The checksum file is checked as published, not its PGP signature; the
  trust is the same as when the image was first pinned, renewed against the
  vendor's current copy.
- A base that no longer matches its download can only be imported again; a
  re-receipt never blesses changed bytes.
