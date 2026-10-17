# A failed vault dialog could grant consent

## Failure

The host confirmation helper accepted an allow button from the dialog's
standard output even when the dialog exited unsuccessfully or was terminated.
It then exited successfully itself, so the relay's own exit-status check
could not distinguish that failure from the operator's consent.

## Cause and fix

`hyperlab-vault-confirm.answer` mapped standard output to a decision without
checking the dialog's return code. It now returns `deny` on every nonzero
return code before interpreting output. Successful button selections retain
their existing behavior; the guest never decides whether a signature is
authorized.

## Regression proof

`tests/vault_relay_contract.py` supplies a failed dialog with each allow
button and exit codes 1 and -15. Before the fix it failed with
`a failed dialog (exit 1) authorized 'Allow once'`; after the fix it passes.
The existing successful selections, unknown buttons, missing executable,
malformed call and relay refusal tests remain in the same suite.

This verifies software behavior with a simulated dialog. It is not evidence
of a failure observed on the lab or on Nitro.
