# Ly rejected an unsupported configuration validation command

Author: [importriri](https://github.com/importriri).

Status: resolved on Nitro.

## Symptom

The desktop apply tried to validate each edited Ly setting through a
`--validate-config` command-line option.

The installed Ly build rejected that argument and aborted inside the validation
path. Ansible reported the same failure for successive palette keys, so a
syntactically ordinary color edit could not converge.

## What was wrong

The role had made an assumption about Ly's command-line interface that was not
part of the installed package contract.

The configuration file itself is package-managed and contains many settings
outside HyperLab's palette scope. Replacing the whole file or inventing a
validator would both create a larger ownership boundary than the theme needs.

## Fix

Keep the complete package-managed `/etc/ly/config.ini`.

Before editing, read it and require every HyperLab-owned key to exist exactly
once. Change only those reviewed keys. Read the file again and require every
requested value to have landed exactly once.

Everything else in the package configuration survives untouched.

## Regression proof

The Nitro desktop apply subsequently passed the pre-edit uniqueness checks,
targeted edits and post-edit exact-value checks, followed by idempotent desktop
convergence.

The contract is package ownership plus targeted mutation, not wholesale
configuration replacement.
