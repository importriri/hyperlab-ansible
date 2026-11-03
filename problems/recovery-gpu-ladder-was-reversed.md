# Recovery GPU readbacks used a second, reversed ladder

## Observation

The Nitro capture session on 2026-11-02 showed Clean/Dev 0 through Lab 3 in
`hyperlabctl open manager --section gpu`. The Networks detail for Dev said
"GPU rank 0". The CLI and visual trust contract instead specify
clean 3 → dev 2 → dirty 1 → lab 0, with Services outside the ladder.

## Cause and fix

The GTK recovery surface held its own GPU rung tuple and two literal rank
maps, used by the Create inspector and Networks dock. They disagreed with
`gpu_trust_levels` in `group_vars/all/networks.yml`.

All three readbacks now consume the status document's `trust.ladder` from
`TrustProvider`, the same provider that `hyperlabctl trust` uses. They sort
by descending rank, refuse an incomplete or invalid ladder, and show
Unknown/unavailable when it cannot be read. Services has no implied rank.
The current owner marker uses its reported GPU handoff profile, including
for a Machine whose network is Services; it never derives that profile
from the network identity.

The M11 contract previously required this defective implementation. Proposed
[ADR 0055](../docs/adr/0055-recovery-readback-verification.md) explains why
those literal requirements are replaced by the executable checks below.

## Regression proof and remaining gate

`tests/recovery_gpu_ladder_contract.py` executes the real CLI trust command
and provider on controlled inputs, then inspects real GTK widget structure
for GPU, Networks and Create. Changing the supplied ladder changes all
three readbacks, proving there is no independent rank table. Missing and
invalid inputs never produce a fallback ladder. Reintroducing the reversed
map or a literal rank in either detail fails.

Reopen GPU and Networks on Nitro and compare with `hyperlabctl trust`.
The physical presentation remains unverified here.
