# Signed DKMS modules did not have a proved kernel trust path

## Symptom

Both `kvmfr` and `linuwu_sense` contained SHA-512 signatures from the same DKMS
module signing certificate, yet the running kernel taint value included the
out-of-tree/untrusted-module flags.

The DKMS certificate was not visible in the audited secondary or machine trusted
keyrings.

## Root cause

A module carrying a signature is not equivalent to a module whose signer is
trusted by the kernel under the selected enforcement policy.

The audited kernel currently has module-signature support but does not force
signature enforcement. The active VFIO profile also leaves lockdown at `none`.
That permissive state allows the modules to work today but does not prove that
they will load under a future stricter lockdown/module-enforcement policy.

## Fix

Do not reuse the Secure Boot db private key as an ad-hoc daily DKMS build key and
do not claim the current DKMS signature as trusted-module proof.

Keep module trust as a separate acceptance gate. Before enabling a stricter
module-enforcement policy, define and test an explicit signing/trust path for
all required out-of-tree modules.

## Proof

The pre-enrollment audit recorded the DKMS certificate fingerprint, current
kernel keyrings, module signers, module-enforcement state and kernel taint.

## Status

OPEN. Close only after the chosen kernel enforcement policy accepts freshly
built `kvmfr` and `linuwu_sense` through a documented trust path and the
post-reboot runtime gates remain green.
