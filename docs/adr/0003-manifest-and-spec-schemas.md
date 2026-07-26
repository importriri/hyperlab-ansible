# ADR 0003 - Image manifest and VM spec schemas

## Context

Six images and an open-ended set of VMs need to be described somewhere
that both Ansible and a CLI can read, without either of them becoming the
definition. The descriptions must survive schema changes and must never
carry secrets or binaries into Git.

## Decision

Two versioned YAML schemas, `schema_version: 1`, in `schemas/`:

- **image manifest** (`images/<id>.yml`) - identity, format, checksum,
  size, what it supports (`standard`, `vfio`, `cloud_init`, `qga`), what
  it requires (`uefi`, `secure_boot`, `tpm2`, `min_memory_mb`),
  redistribution status, and declarative defaults;
- **VM spec** (`vm-specs/<name>.yml`) - image id, lifecycle, hardware
  profile, network profile, resources, and the policy fields
  (clipboard, shared folders, USB allowlist, snapshot and backup policy).

Validation is a plain Python script over PyYAML - the same dependency
`tests/static_contract.py` already uses. No `jsonschema`, no `pydantic`:
the validator has to run on the blind host with only what the lab bundle
installs.

The manifest describes the artefact; the spec describes an instance.
They never restate each other: a spec names an image id and nothing else
about it.

## Consequences

- Binaries stay out of Git; the manifest carries a SHA-256 and the image
  arrives on a disk.
- `private: true` and `contains_personal_data: true` are schema fields,
  so "never publish this" is checkable instead of remembered.
- Adding a seventh image is one file plus one validator run.
- A schema change means `schema_version: 2` and a migration note, not a
  silent reinterpretation of existing files.
