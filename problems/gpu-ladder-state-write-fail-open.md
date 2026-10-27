# The GPU ladder accepted a start whose rung it could not record

Found by an architecture review of `roles/gpu_handoff/files/qemu`, not by a
failure on a host. No run on Nitro is known to have hit it.

## What was wrong

The qemu hook read `/run/gpu-handoff/trust`, compared the request and wrote
the new rung with `printf '%s\n' "${trust}" > "${STATE_FILE}"`, then
`exit 0`. Two things were missing.

- The write status was never looked at. If the state could not be written, a
  dirty domain took the GPU while the record still said clean, and a later
  clean domain passed. The truncating redirection could also leave an empty
  file behind.
- Nothing serialized the read and the write. The managed start holds its GPU
  lock around `virsh start`, but a manual `virsh start` or an autostart does
  not, and libvirt may run `prepare` hooks for different domains at the same
  time. A clean request that read the fresh-boot state, paused, and wrote
  after a dirty request had committed left 3 recorded over a GPU that dirty
  code had used.

Both break "lower, never raise" without any policy file being wrong.

## Fix

The read, the comparison and the commit are one transaction under a
hook-owned `flock` on `/run/gpu-handoff/lock`, created `0600` so no other
user can hold it. The new rung is written to a `mktemp` file in the state
directory, made `0644` for the unprivileged desktop reader, and renamed over
`trust` with `mv -f -T`. Every step's failure refuses the start, the EXIT
trap removes the hook's own temporary file, and the previous `trust` stays
byte-identical. A symlinked state directory, lock or trust file is refused.
[`docs/gpu-handoff-policy.md`](../docs/gpu-handoff-policy.md) describes the
transaction.

## Failure injection

`chmod` cannot make a write fail when the battery runs as root, and nothing
here may touch the real `/run/gpu-handoff`. The tests use fixture state
directories and break one thing at a time:

- the write: `trap '' XFSZ; ulimit -f 0` before running the hook. The file
  size limit binds root as well, and with SIGXFSZ ignored the write returns
  EFBIG to `printf`, a real short write;
- `flock`, `mktemp` and `mv`: a replacement on `PATH` that exits 1, or that
  sends TERM or KILL to the hook in the middle of the commit;
- the race: wrappers around the real `flock` and `mktemp`. The lock stays the
  real `flock(2)`; the wrappers only report whether the lock was held and
  pause one request between its read and its commit until the test opens a
  FIFO gate. Every wait has a bound; there is no sleep.

## Test

`tests/hook.bats`, the tests after "the state transaction". With the lock
condition replaced by `false`, "concurrent prepares: a stale cleaner commit
cannot overwrite a dirtier rung" fails on `[ "$(state)" = "1" ]`: the rung is
3, the old race. With the write status ignored, the two write-failure tests
fail because an empty rung is published. The full list of breaks is in
`tests/MUTATIONS.md`, "The GPU ladder state is committed without its
transaction".
