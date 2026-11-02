# Palette preview parser errors escaped the refusal diagnostic

Status: software-verified with temporary source fixtures.

## Symptom

`palette-summaries --json` returned exit 1 and empty stdout for some malformed
inputs, but printed a Python traceback instead of the registry diagnostic.
An unused YAML value such as `bad_date: 2026-13-45` was enough to trigger it.

## Root cause

YAML constructs date-shaped scalars while loading the document. An invalid
date raises plain `ValueError`, outside the caught YAML exception family.
JSON integer conversion can also raise `ValueError`; deeply nested JSON or
YAML can raise `RecursionError`. None reached the ordinary refusal handler.

## Fix

The preview readers convert these parsing exceptions to `ThemeError` with
the input path and format. All rows still validate before any output, and
the existing handler returns the registry prefix without a traceback.

The preview also keeps one root directory descriptor for all input reads.
Previously it reopened the resolved path for every input, allowing a renamed
ancestor of the checkout to change which tree supplied later files.

## Regression proof

`python tests/theme_registry_contract.py` executes the real CLI with invalid
dates in each YAML input, 5000-digit JSON integers and excessive JSON/YAML
nesting. Every case requires exit 1, empty stdout, the registry diagnostic
and unchanged input/HOME/XDG snapshots. An audit hook requires exactly one
root-path open. Separate parser and root-reopen mutations fail the contract;
restoring each returns green. No installed state or physical result is claimed.
