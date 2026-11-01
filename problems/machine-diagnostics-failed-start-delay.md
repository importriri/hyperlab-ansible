# Diagnostics waited for the collection deadline after a failed start

Status: software-verified; installed-shell observation remains pending.

## Failure

If the diagnostics bridge could not start, the process transport could remain
not running without emitting an exit signal. Only the 750-second collection
deadline settled the request, so the pane stayed busy and refused a retry
for twelve and a half minutes despite having no collection in progress.

## Fix

Arm a separate five-second startup check before requesting process launch.
If the bridge is still not running, return the correlated failure with no
archive and stop both timers. A running bridge keeps its full collection
deadline. Old timer and exit callbacks cannot settle a newer request.

## Regression evidence

`tests/host_operation_qml_contract.py` executes the production transport
component with inert process I/O. It checks the five-second bound, a running
bridge surviving that check, failed-start settlement without an exit signal,
stopped timers, retry and late callbacks. The new scenario failed before the
startup check existed and passed after it was added. Disabling its settlement
handler makes the contract fail again. No installed process or Machine was
used; physical collection remains a separate gate.
