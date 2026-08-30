# sbctl export-enrolled-keys failed at the Landlock/output-directory boundary

## Symptom

A read-only attempt to export the currently enrolled firmware certificates with
`sbctl export-enrolled-keys --dir ...` failed in two opposite states:

- with a missing output directory, Landlock rejected the path before `sbctl`
  could create it;
- with a pre-created directory, `sbctl` rejected the directory because the
  command expects to create it itself.

## Root cause

This is an upstream `sbctl` tooling defect at the interaction between its
Landlock path rules and output-directory creation. It is tracked upstream as
Foxboron/sbctl issue 410.

The failure did not modify EFI variables.

## Fix

For this narrow read-only export operation, HyperLab used:

`sbctl --disable-landlock export-enrolled-keys --dir <new-path> ...`

The output path was not pre-created. Landlock remains enabled in the normal
`sbctl` configuration; the sandbox is disabled only for this affected export
command.

## Proof

The workaround exported the Acer/Microsoft/ABO PK, KEK and db certificates.
Subsequent `sbctl status` still reported Setup Mode disabled and Secure Boot
disabled, proving that the audit had not enrolled or replaced firmware keys.

## Status

Workaround validated on `sbctl` 0.18. Keep the exception narrow until the
upstream behaviour is fixed and the installed version has been re-tested.
