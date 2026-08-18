# Nitro Sense DKMS cleanup happened too early in a managed update

Author: [importriri](https://github.com/importriri).

## Symptom

Updating an already managed Linuwu-Sense build could remove the previous DKMS
source or version before the replacement driver had completed its build,
installation and runtime validation.

That ordering weakened the recovery path precisely while the platform driver
was being replaced.

## What was wrong

A managed-to-managed update is not equivalent to a fresh install. The previous
module is the known recovery candidate until the new source has compiled, DKMS
has installed the exact target for the running kernel, the new module has
claimed the Acer platform device and the required sysfs interface has passed
post-load checks.

Cleaning the superseded version earlier made repository tidiness more important
than transaction safety.

## Fix

Treat the update as a staged transaction.

The target source is copied and patched in an isolated build probe first. The
same reviewed source is then prepared for DKMS and built for the running
hardened kernel. The platform-driver transition happens only after those gates
succeed.

The superseded managed DKMS version and source directory are removed only after
the new driver is active and the configured runtime settings have been read
back successfully.

The previous installed version is retained as the failure-recovery candidate
until that point.

## Regression evidence and remaining proof

The final AN515-55 runtime state showed managed version `6b45d4439e68` installed
for `7.1.8-hardened1-2-hardened`, `linuwu_sense` loaded from the DKMS module
path, the full source stamp updated to the target overlay, fan policy at
`100,100` and battery limiter at `1`.

The source ordering now retains any superseded managed version until the new
runtime and settings are proved. No cleanup step is allowed to run merely
because a newer source identity was requested.

This campaign does not prove the exact `b4db5e3da23f` to `6b45d4439e68`
transition operation under the final code, because the target state was already
present when the expected real transition was observed. That provenance gap is
tracked separately. A future intentional managed version bump must capture both
pre- and post-transition identities before this lifecycle is called fully
hardware-proved.
