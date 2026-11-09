# Resident refresh rejected a symlinked checkout

Author: [importriri](https://github.com/importriri).

Status: corrected in source and software-verified. Installed Nitro apply
and Predator replay remain pending.

## Symptom

A Nitro host apply stopped at "Refresh the running HyperLab shell" with
`RuntimeError: Redirected checkout pointer`. Check mode passed because it
does not dispatch resident refresh. The same code passed directory-based
fixtures, which did not reproduce the installed checkout layout.

## Root cause

The regular `/etc/hyperlabctl/checkout` file named the configured checkout,
whose final component was an admin-owned symlink to the actual repository.
`provenance_source()` required the checkout's resolved path to equal its
literal spelling. This rejected a configuration accepted by the provenance
bridge, which launches the resolver with the literal checkout path in argv.

## Fix

Resolve the checkout for resolver validation and generation hashing, while
matching the running observer against the pointer's literal checkout and
resolver arguments. Checkout symlinks in the final component or an ancestor
are accepted. The pointer must still be a regular single-line absolute path;
missing inputs, a symlinked resolver and a redirected tools directory remain
refusals. Neither the pointer content nor the observer launcher changes.

The refresh runs as the same admin user who already controls the checkout
and its symlink. Accepting that path gives the user no additional authority.

## Regression proof

`symlinked_checkout_contract` in
`tests/shell_reload_after_apply_contract.py` reproduces both layouts with
temporary files. It requires successful generation, resolver-content
sensitivity and exact literal observer matching, and refuses missing or
redirected resolver inputs. Existing pointer and argv refusals still run.
The corresponding mutations are recorded in `tests/MUTATIONS.md`.
