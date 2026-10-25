# A refused projection left the Machine record behind

Found while holding `privatestack-machine-actions create` to ADR 0017
("A refusal leaves no record behind"), on `main` at 3191615.

## What was wrong

The bridge ran `hyperlabctl machine create` and then `machine project`. When
`project` refused after `create` had succeeded, for example because a stale
`vm-specs/.generated/NAME.yml` was in the way, the bridge reported the
refusal and stopped, but the record `create` had written stayed in
`$XDG_STATE_HOME/hyperlab/machines`. Sending the same request again was then
refused by `create` with "already exists", for a Machine the shell had been
told was not created. A timeout or a malformed answer from `project` did the
same.

A second, quieter gap sat in the factory. The creation plan reported the
custom memory floor as the image's `min_memory_mb`, but
`_resource_values` held a custom request only to the generic 512 MB. The
bridge compared the request with the plan, so the shell could not go below
the floor, but `hyperlabctl machine create --resource-profile custom` could,
and ADR 0017 says everything the shell submits is re-validated by the
factory.

## Fix

- `hyperlabctl machine create --project` records and projects in one staged
  step under the registry lock: the name is checked, the spec is written,
  and the record is published last. When the record cannot be published,
  the spec this step wrote is removed while it still equals the projection.
  The bridge creates Machines only this way.
- A first fix kept two calls and had the bridge withdraw the record after a
  refused `project`. Review showed it could not always do so: `withdraw`
  rightly refuses when libvirt cannot be read, and a symlink or a directory
  where the spec goes refused the withdrawal too. Staging removes the need
  to undo a published record.
- `hyperlabctl machine create` reports `record_sha256`, the digest of the
  record as stored.
- `hyperlabctl machine withdraw NAME --record-sha256 DIGEST` removes that
  record only while its bytes still have the digest, and refuses when a
  generated spec equal to the record's projection exists, when libvirt
  lists a domain with that name, or when the domain list cannot be read:
  such a Machine got past intent and is not withdrawn. A first version
  looked only at the spec, which can be removed by hand while the domain
  stays ([ADR 0053](../docs/adr/0053-withdraw-machine-intent.md)).
- `create`, `project` and `withdraw` hold the registry lock, so a record is
  never withdrawn while its spec is being written. `withdraw` remains for
  the manual path.
- The bridge starts provisioning only on an answer naming this Machine, its
  spec `vm-specs/.generated/NAME.yml` and a lowercase SHA-256.
- `machine_factory.custom_limits()` is the one place the custom limits are
  computed. `_resource_values` enforces the memory floor through it and the
  creation plan reports it.

## Test

`tests/c10_machine_create_plan_contract.py` runs the real bridge over the
real CLI in a temporary checkout and state home. With a stale spec, a
symlink or a directory where the spec goes, with libvirt unreadable, and with
the record's publication forced to fail after the spec was written, the
registry and the generated specs are byte-identical before and after. With
the bridge back to `create` then `project`, it fails on its first such case
with "a refused projection left a record on a fresh registry: ['.lock',
'srv-01.yml']". The same contract creates a record at each custom
limit and one unit below it; with the floor check removed from the factory
it fails with "the factory accepted memory_mb=..., below the plan's limit".
