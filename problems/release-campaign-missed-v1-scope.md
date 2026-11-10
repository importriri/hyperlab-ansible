# The release campaign could not describe the selected v1

## Failure

The historical v2 campaign required Jellyfin and service recovery, but had
no place to record both server distributions, permanent creation through the
shell, disposable stops, per-run GPU lease or the full Showcase. Its
canonical-plan check correctly refused a different scope. Sealing a valid
v2 campaign therefore could not qualify v1.

The release input readers also silently replaced duplicate YAML/JSON keys
and followed redirected campaign files. A duplicated observation could hide
a false value; a redirected plan was not an independent regular input.

## Fix

A separate `release/acceptance.v3.yml`, described by Proposed ADR 0063,
records 19 ordered gates for the selected v1. Clean GPU use precedes dev;
Create, access, audio, lease and Showcase precede dirty/lab tests; reboot
and recovery follow. Each distribution and each stop/recovery outcome has
its own observation. The initial lease is `workstation-dev-standard`,
default without GPU, with the ladder unchanged on the GPU-less run.
Jellyfin and service recovery remain in unchanged historical v2 only.

The runner propagates the selected integer version through plan, scaffold,
evidence and receipt; it refuses unsupported and mixed versions without
migration or pass import. New booleans share the existing strict type/truth
guard. Failed gates may retain false and cannot seal. Campaign readers now
refuse duplicate keys, non-regular files and symlink redirection. The probe
also validates its generated payload against the same scalar contract.

## Regression evidence

The independent field oracle enumerates both scopes and every field class.
It compares the v3 manifest, ADR table and fixture plans. Real CLI fixtures
cover both versions/profiles, all false observation passes, edited evidence,
failed/pending campaigns, deterministic receipts and unchanged bytes on
refusal. Every boolean is exercised through record with strings and integers
in both passed and failed records, including the former record-only
coercion coverage gap. The probe rejects boolean --value coercion and keeps
--true/--false typed. Storage and idempotence collectors use both manifests.

The documentation contract parses manifest flags and gate order and executes
the complete synthetic command sequence for both profiles. The unchanged
bootstrap required-mode verifier compares its real fixture writer with the
storage guard and historical v2 manifest; independent complete v2/v3 mapping
equality extends only that storage agreement to v3.

The scope, typing, read-path truth, record-only coercion, mixed-version,
storage, input-refusal and runbook mutations in `tests/MUTATIONS.md` were
observed red and restored green. These are software fixtures. No real
campaign was read, rewritten, upgraded or sealed; no hardware observation
or publication was made. Debian image preparation, real lease controls,
portable Predator checks, recording and all frozen physical observations
remain pending.
