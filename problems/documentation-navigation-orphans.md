# Top-level documentation contracts were not reachable from repository navigation

Author: [importriri](https://github.com/importriri).

Status: candidate fix; full verifier rerun pending.

## Symptom

The documentation contract rejected newly added top-level documents as
orphans. A complete audit found four files without any inbound Markdown link:

- `docs/golden-image-control-center-contract.md`
- `docs/nitro-control-backend.md`
- `docs/nitro-control-panel.md`
- `docs/visual-trust-contract.md`

The files existed and their content was valid, but they were not reachable from
the repository documentation graph.

## Root cause

The documents were added while their implementation work was still being
validated, but the repository map was not extended at the same time.
`tests/docs_contract.py` deliberately requires every top-level Markdown file in
`docs/` to have an inbound link so operator and architecture contracts cannot
become undiscoverable files.

The first repair attempt linked only the first orphan reported by the contract.
Because the test stops at the first failure, that attempt exposed the next
orphan and rolled back without changing the candidate.

## Fix

The `README.md` operator and architecture map now links all four audited
documents. The repair preflight records the complete orphan set before writing,
so a new or missing orphan cannot be silently folded into the change.

No document body or runtime behavior is changed.

## Regression gate

`tests/docs_contract.py` must report no orphaned top-level documents and the
complete `./verify.sh` run must pass.
