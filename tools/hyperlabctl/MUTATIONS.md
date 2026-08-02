# Mutations

Every mutation below was applied, the suite executed, the result recorded, and
the file restored. A mutation that does not turn the suite red is reported as
green with the reason, not quietly dropped.

| # | File | Mutation | Result | Assertion that caught it |
|---|------|----------|--------|--------------------------|
| 1 | `document.py` | catch `ValueError` instead of `Exception` | red | `test_document_survives_a_crashing_provider` |
| 2 | `providers/memory.py` | drop the VFIO fixed overhead term | red | `overhead_mb` expected 768, got 512 |
| 3 | `providers/domains.py` | invert the blocked comparison | red | `test_stopped_domain_reports_how_much_it_is_short` |
| 4 | `providers/gpu.py` | `all()` becomes `any()` when deciding `bound` | red, after a test was added | `half_bound_not_bound` |
| 5 | `providers/trust.py` | a claimed level reports `can_ascend: true` | red | `claimed_can_ascend` |
| 6 | `registry.py` | the unprivileged filter returns everything | red | `action_vm.create_subcommand_exists` |
| 7 | `render.py` | waybar payload grows a fifth key | red | `waybar_keys` |
| 8 | `operations.py` | `start` no longer checks the budget | red | `refused_exit_code` expected 2, got 0 |
| 9 | `providers/__init__.py` | remove the discovery import loop | red | `status_exit_code_error` |
| 10 | `panel/model.py` | the footer offers start on a blocked domain | red | `start_disabled_when_blocked` |
| 11 | `panel/model.py` | the selection is no longer clamped to existing rows | red | `test_selection_is_clamped_to_the_rows_that_exist` |
| 12 | `remedies.py` | one problem loses its remedy | red, after a test was added | `no_problem_without_a_remedy` |
| 13 | `journal.py` | priority 4 read as info instead of warn | red | `warn_level` |
| 14 | `render.py` | an unreadable pill stays yellow instead of going red | red | `unreadable_class` |
| 15 | `operations.py` | the refusal no longer names the shortfall | red | `refusal_states_the_shortfall` |
| 16 | `providers/__init__.py` | a broken extension becomes fatal | red | `test_a_broken_extension_does_not_stop_a_good_one` |
| 17 | `panel/views.py` | two views may claim the same key | red, after a test was added | `duplicate_view_key_refused` |
| 18 | `panel/model.py` | the gauge is no longer clamped to 0..1 | red | `gauge_width_2.0` expected 14, got 28 |
| 19 | `commands/watch.py` | `watch` keeps looping with no virsh | red, after a test was added | `watch_bailed` |
| 20 | `config.py` | an override is ignored | red | `nitro_status_exit` |
| 21 | `commands/net.py` | an inactive network is reported active | red | `lab_inactive` |
| 22 | `providers/images.py` | sealed without a checksum stops being an error | red, after a test was added | `sealed_without_checksum_flagged` |
| 23 | `registry.py` | an unavailable action is offered anyway | red | `no_available_action_may_reference_a_missing_playbook` |
| 24 | `cli.py` | remove global-option normalization, so `actions --json` is rejected | red | `test_global_json_flag_is_accepted_after_the_subcommand` |
| 25 | `runner.py` | stop forcing the C locale for parsed subprocess output | red | `test_runner_forces_machine_parseable_locale` |
| 26 | `runner.py` | turn explicit `timeout=None` back into the default timeout | red | `test_runner_preserves_an_explicit_no_timeout` |
| 27 | `commands/watch.py` | treat every libvirt failure like a heartbeat timeout | red | `test_watch_stops_on_a_real_libvirt_error_instead_of_spinning` |
| 28 | `registry.py` | allow `vm-specs/` to redirect outside the repository | red | `test_target_choices_refuse_a_redirected_spec_directory` |
| 29 | `operations.py` | let a managed M3 domain use direct `virsh start` | red | `test_managed_domain_cannot_bypass_the_m3_start_playbook` |
| 30 | `operations.py` | start anyway when the memory budget cannot be read | red | `test_start_refuses_when_the_memory_budget_cannot_be_read` |
| 31 | `operations.py` | start a VFIO domain absent from `gpu_domain_profiles` | red | `test_unguarded_vfio_domain_cannot_start_from_the_cockpit` |


## Cockpit/M3 integration mutations

Mutations 24-31 were replayed after the semi-final cockpit was integrated with
M3. All eight turned the component suite red. They pin the defects found in
review rather than only the original design: shell-surface option order, stable
locale, the watch heartbeat timeout, repository target containment, and the
three fail-closed boundaries around managed, over-budget and unregistered VFIO
domains.

## Mutation 4 survived the first run

`all()` to `any()` was not killed, because the only unbound fixture put both
PCI functions on non-VFIO drivers, where `any()` is false as well.

The state that separates them is the mixed one: VGA on `vfio-pci`, audio still
on `snd_hda_intel`. That is not hypothetical - it is what the Nitro reported on
19/07 when the profile IDs did not match the installed card. A test for it was
added (`test_gpu_half_bound_is_not_bound`), and the mutation was replayed and
seen red on `half_bound_not_bound`.

The gap was in the tests, not in the code. The mutation is what found it.


## Mutation 12 survived the first run

Deleting the `gpu.not_bound` remedy changed nothing, because the only test that
walked the remedies used a host with no hardware profile, where the GPU section
fails earlier with a different problem id. The remedy table was checked by
accident, not on purpose.

`tests/test_remedies.py` now scans the provider sources for every declared
problem id and asserts the table covers all of them, so a new problem arrives
with its remedy or the suite says so. The mutation was replayed and is red.

## A mutation replay can lie to you

Mutations 13 and 14 first reported red for the wrong reason: mutation 13
replaces `warn` with `info`, which leaves the file byte-for-byte the same
length, and with a coarse mtime Python reused the cached bytecode from the
mutated run after the file had already been restored. The suite was reporting
on code that was no longer on disk.

Every mutation in this file was replayed with `PYTHONDONTWRITEBYTECODE=1` and
the caches removed. Same-length edits are the dangerous ones: a mutation that
changes the file size hides this bug instead of exposing it.


## Three more survived their first run

- **17** - nothing asserted that two views may not claim the same key, so the
  guard could be deleted silently. `test_two_views_may_not_claim_the_same_key`
  now does.
- **19** - `watch` bailing out when virsh is absent had no test. It does now,
  and the mutation is interesting: without the guard the suite does not fail,
  it *hangs*, because the loop never terminates. The replay harness runs each
  mutation with a timeout and treats a hang as red, which is the honest reading.
- **22** - the sealed-without-checksum rule was never exercised, because the
  fake host only carried a `not-built` manifest. The fixture takes extra
  manifests now, and both the violating and the clean case are pinned.

## A mutation replay can lie to you, twice

Mutations 13 and 14 first reported red for the wrong reason: replacing `warn`
with `info` leaves the file exactly the same length, and with a coarse mtime
Python reused the bytecode from the mutated run after the file was restored.

Then a replay timed out mid-run and left `commands/watch.py` mutated on disk,
which quietly poisoned the next three test runs until the diff was read. Both
lessons are in the harness now: `PYTHONDONTWRITEBYTECODE=1`, a per-mutation
timeout, and the restore in a `finally`.


## What the linter found that the suite did not

`ruff check` with pyflakes and bugbear selected found four unused imports, a
loop variable that was never read, and eight places where an exception was
re-raised without its cause - which on a diagnostic tool is the difference
between "PyYAML is not importable" and knowing which import failed.

It also caught a defect introduced while fixing those: `raise ... from exc` in a
handler that had never bound `exc`, which would have raised `NameError` on the
one path it was meant to describe. The suite did not catch it because that path
only fires on a host without PyYAML. `ruff.toml` records the ruleset so the
check is reproducible rather than a one-off.
