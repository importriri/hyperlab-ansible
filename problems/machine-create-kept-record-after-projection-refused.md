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
- The staged step first treated `os.link` as the end of the publication.
  `create_machine()` then inspected the record and synced its directory,
  and `_create` read it back and took its digest; a failure at any of
  those steps was reported as a refusal while the record stayed, and the
  spec it projects was removed. A retry said "already exists" again, for a
  record now without its spec. The publication now returns which file it
  put in place (`PublishedRecord`: path, inode, digest), and the creation
  undoes it under the lock with `withdraw_published()`: the record first, only while
  it is the same inode with the same bytes, then the spec, only once the
  record's removal is synced and only while the spec is the file this
  creation wrote. When either cannot be removed, the refusal says "cleanup
  incomplete" and names what stays.
- That first undo knew the publication only from an exception class
  raised for `Unavailable` and `OSError`. A `KeyboardInterrupt` at the
  inspection or the directory sync after `os.link` reached the undo
  without it, so the undo removed the spec and kept the record: the very
  state it exists to prevent. The publication is now announced to the
  caller (`announce=`) before `os.link`, and every exception after that
  is undone the same way; a record that is not where it was announced
  counts as gone only once its directory is synced. `create_machine()`
  had the undo without the registry lock; it now holds the lock across
  publication and undo, as the CLI does.
- `withdraw` first read the generated spec with `load_yaml` and took a
  spec that did not parse for "not what project writes", so malformed YAML
  or two YAML documents let it remove the record. It now reads the spec
  through `read_generated_spec()`: only a missing file is "no spec"; a link,
  anything but a regular file, an unreadable or non-UTF-8 file, malformed
  YAML, several documents or a repeated key (which `safe_load` silently
  accepts) is a refusal, and only a spec that parsed is compared with the
  projection.
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

`check_publication_faults` runs the real bridge over the real CLI, with
faults installed in the CLI's own process: the directory sync after the
real `os.link`, the read-back and the digest fail once, and the registry
and the generated specs equal their snapshot, with nothing sent to the
runner. The record's removal failing, the record or the spec replaced and
the removal's own sync failing are reported as "cleanup incomplete", with
the replaced bytes kept and the spec kept while the record stays. With the
undo of the published record removed, the first case fails with "['fsync']:
a creation refused with the record published left a record or spec
behind". Every removal is checked to run while the registry lock is held.
A `KeyboardInterrupt` right after the real `os.link`, at the inspection and
at the directory sync is undone the same way; with the undo limited to
`Exception` again it fails with "['interrupt-after-link']: ... left a record
or spec behind (record kept: True, spec kept: True)", and with the
publication announced only once complete, "['fsync']: ... (record kept:
True, spec kept: False)". A read-back digest of other bytes is refused and
undone. `tests/c10_machine_registry_contract.py` holds `create_machine()`
to the same undo and to the lock: another process holding it makes the
creation refuse as busy and change nothing.

`check_withdraw_reads_the_spec` puts each unreadable spec in the way of a
withdrawal through the real CLI and loader and requires a refusal with the
record and the spec byte-identical. With the parse failure turned back into
`None` it fails with "withdraw went on with a malformed spec: 0".
