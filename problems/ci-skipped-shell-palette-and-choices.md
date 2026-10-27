# CI skipped the shell, palette and choices checks

The local verifier ran shell structure at level 0f and five palette/choices
commands at level 0g. The required CI validation job ran neither group. Its
discovered contracts did not cover these standalone suites, so a regression
could fail locally and pass CI. The existing static discovery checks only
protected the contract and refusal glob patterns.

## Fix

Two unconditional steps in the existing `validate` job run the same commands
and arguments as the local verifier:

```sh
sh tools/shell-tests/run.sh
python3 tools/palette/audit_palette.py tools/palette/palette.yml
python3 tools/palette/verify_surfaces.py roles/host_desktop_sway/files/palette
python3 tools/choices/choices.py check
python3 tools/choices/test_choices.py
python3 tools/choices/test_consistency.py
```

They use the job's default fail-on-error shell, without `continue-on-error` or
event guards. Existing discovery, the cross-repository job and failure
diagnostic uploads remain in place.

## Regression proof

`python tests/ci_verify_parity_contract.py` parses the workflow and executes
the validation run blocks and the whole local verifier in a temporary checkout.
Recording command stubs provide the observed argv. A separate fixed list of six
expected invocations prevents a matching mistake in both entrypoints from
passing. Every command runs once on the successful path. Each stub then fails
independently, and both entrypoints must return failure.

The toolchain step has an explicit id so the fixture can exclude installation.
Its restricted PATH contains recording stubs and file utilities only. Render
uses a dummy password file and a stubbed playbook command. No fixture invokes
sudo, package installation or the network. Unsupported workflow execution
settings, duplicate YAML keys/step ids and redirected input files are refused.

`python tests/contract_mutations.py CiVerifyParityMutationTests` checks removed
commands, comments or unreachable commands, optional steps/jobs, argument
drift, ignored child statuses, pipelines and successful commands that mask a
failure. The committed workflow before the added steps fails the behavioral
contract for all six missing invocations; the corrected workflow passes.

This is software coverage of the two entrypoints. It does not qualify hardware,
resolve independent Showcase failures or replace privileged render tests.
