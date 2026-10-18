# A PipeWire failure before the initial format hung the sender

## Failure

The sender waited forever if PipeWire reported a stream or core failure
before delivering its first format. The callback set `streamFailed` and
signalled the loop, but initialization checked only `hasFormat` and went
back to sleep. Capture's existing failure handling was never reached.

## Fix

The initial-format wait also checks `streamFailed` and `stop`. A failed or
stopped initialization unlocks the loop and follows the existing cleanup
path, returning failure instead of waiting again. Silence during an already
streaming capture retains its existing behavior.
The role's patch digest and contract pin change together, so an installation
cannot silently retain the previous binary. This new patch has no Nitro
acceptance receipt.

## Regression evidence

`tests/looking_glass_sender_capture_contract.py` compiles the shipped patch
with the real PipeWire thread loop and simulated portal/stream setup. It
executes the exact initialization tail extracted from the patched source.
The new scenarios deliver stream ERROR, UNCONNECTED and a core error while
initialization waits for its first format.

Before the fix, the first scenario exited 1 with
`initial-failure-0: the harness itself hung` after the five-second deadline.
After the fix, the contract exited 0 with
`Looking Glass sender capture contract: OK`: all three initial-failure
scenarios and the existing teardown, late-format, flow, missed-wakeup,
silence and streaming-failure scenarios passed. This focused software test
does not constitute a full gate or Nitro acceptance.

Sid's subsequent full gate exited 1: the offline VFIO hardware contract
still expected the runtime patch's previous digest even though the role
and Linux sender contract already pinned the corrected patch. The guest
gate correctly reads the role's digest and compares it with the installed
build stamp. This is consistent with ADR 0045's requirement to use the
rebuilt sender rather than infer health from an old build. No guest gate
behavior or acceptance threshold needed changing.

The offline hardware contract now compares the loaded runtime digest with
SHA-256 of the actual shipped patch bytes. This still rejects a stale role
digest, and the Linux sender contract separately pins the reviewed digest.
Before this contract correction, the targeted hardware test exited 1 at
`load_expected_transport(ROOT)`; after it, the same test exited 0 with
`arch-dev-vfio hardware gate contract: OK`. A temporary fixture restoring
the previous role digest is rejected by the corrected byte-integrity
comparison, and the Linux sender contract's fixed digest pin still passes.
The failed full gate is not a per-commit green receipt.
