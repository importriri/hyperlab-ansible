# A release gate could pass with its boolean evidence false

## Failure

`tools/release_acceptance.py` checked that a reviewed boolean field held a
boolean, never that it held `true`. A campaign could record and seal
`host-idempotence` with `second_apply_changed_zero: false`, or
`vfio-trust-lifecycle` with `reboot_resets_trust: false`, and `status`
reported it ready to seal. Only `nocow` and `no_sensitive_patterns` had
their own checks in `record_gate`, so an evidence file edited by hand
escaped even those.

The typing had also drifted from the manifest. `BOOL_FIELDS` still listed
the retired `loopback_spice` and lacked `spice_socket_private`, which the
`looking-glass` gate requires. `release_probe.py` therefore refused
`--true spice_socket_private` and forced the operator to type
`--value spice_socket_private=<text>`; the validator then took any text,
`"no"` included, as a pass.

The old contract could not see either problem: its fixtures built only
all-true evidence, and its list of booleans was never compared with the
tool's.

## Fix

`spice_socket_private` replaces `loopback_spice` in `BOOL_FIELDS`. In
`validate_gate_payload`, a passed gate requires every reviewed boolean to be
exactly `True`, after the strict boolean type check. That function is the
one `record`, `status` and `seal` already share through
`validate_partial_evidence`, so a hand-edited pass is refused on reading as
well as on recording. A failed gate may still hold `false`: it stays the
next gate, and a campaign with a failed or pending gate is never ready to
seal. The probe needed no change, since it imports the same set.

## Regression evidence

`tests/release_acceptance_contract.py` classifies every manifest field by
hand, gate by gate, as a boolean, a hash or descriptive text, and compares
that list with the tool's typing. For each of the 17 reviewed booleans, a
fixture campaign whose earlier gates pass is refused when it records that
field false (evidence bytes unchanged) and accepts it in a failed gate; an
all-pass evidence file with that field false is refused by `status` and by
`seal`, which writes no receipt; text and integers are refused in passed and
failed gates. `tests/release_probe_contract.py` checks `--true`, `--false`
and the refusal of `--value` for every boolean, and the real command for
`spice_socket_private`.

Before the fix, the new record, read and typing checks were red; after it,
both contracts are green. The mutations are listed in `tests/MUTATIONS.md`.
These are software regressions on temporary fixture campaigns. No hardware
campaign was run, and existing evidence was neither read nor rewritten: a
stored pass with a false boolean is now refused.
