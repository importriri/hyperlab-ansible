# The Linux sender kept a freed portal session handle after each restart

Author: [importriri](https://github.com/importriri).

Status: corrected in the reviewed portal patch and covered by
`tests/looking_glass_sender_portal_contract.py`; not seen to fail on a
guest.

## Cause found in the code

Found while reading the capture restart path for
[`looking-glass-sender-hung-after-capture-stop.md`](looking-glass-sender-hung-after-capture-stop.md).
`portal_destroySession` in the pinned `portal.c` frees the session handle
and then sets its own parameter to NULL (`sessionHandle = NULL`), not the
caller's handle (`*sessionHandle`). `pipewire_deinit` calls it on every
capture restart, so afterwards `this->sessionHandle` points to freed
memory.

A new capture overwrites it once `portal_createScreenCastSession` starts.
If the re-init fails before that, for example because the portal cannot be
reached while it restarts, `pipewire_init` calls `pipewire_deinit` again,
which closes the freed handle: a crash (the portal is NULL) or a double
free.

## Fix

`portal-compat-runtime.patch` clears the caller's handle
(`*sessionHandle = NULL`).

## Regression proof

`tests/looking_glass_sender_portal_contract.py`, scenario "destroy": after
`portal_destroySession` the caller's handle must be NULL, and closing it a
second time must not call the portal again. Before the fix it fails with
`closing the session left the freed handle in place`.
