# Looking Glass render contract triggered nested Jinja evaluation

Author: [importriri](https://github.com/importriri).

Status: candidate fix; full verifier rerun pending.

## Symptom

The repository-wide verifier failed in the Looking Glass render invariants even
though the role still contained the expected input-patch digest field:

`input_patch_sha256: {{ looking_glass_input_patch_sha256 }}`

Ansible also warned that Jinja constant strings should not contain embedded
templates.

## Root cause

The failing assertion embedded the literal role template inside another Jinja
expression. The test therefore evaluated the inner template while parsing the
assertion and searched the role source for an expanded digest instead of for the
literal template stored in `roles/looking_glass/tasks/main.yml`.

The role contract itself had not regressed. The digest default, stamp
comparison, stamp write and dedicated input contract were all still present.

## Fix

The render assertion now uses a regular expression with escaped braces. It still
requires the source form of the digest stamp, but the assertion text no longer
contains an embedded Jinja template.

No Looking Glass role, default, patch or runtime behavior is changed.

## Regression gate

`tests/looking_glass_client_input_contract.py`, render syntax checks and the
complete `./verify.sh` run must pass without the nested-template warning or the
previous render assertion failure.

## Strict-conditional follow-up

The first nested-template repair changed the assertion to `regex_search`, which
correctly found the literal digest stamp but returned the matched string.
Current Ansible requires assert conditions to resolve to a boolean value and
therefore rejected that successful string result.

The source check now tests the `regex_search` result with `is not none`. This
preserves the same exact source invariant while producing an explicit boolean
under strict conditional evaluation.
