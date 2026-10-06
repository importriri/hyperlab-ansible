# The shell's USB allow was bound to a port, not to the device shown

Author: [importriri](https://github.com/importriri).

Status: corrected; covered by `tests/host_usbguard_contract.py`,
`tests/host_machine_actions_bridge_contract.py`,
`tests/host_operation_lifecycle_contract.py`,
`tests/host_operation_integration_contract.py`,
`tests/host_operation_qml_contract.py`,
`tests/host_quickshell_runtime_contract.py` and
`tools/hyperlabctl/tests/test_registry.py`.

## Symptom

Found in review, before any run on hardware. The USB devices view
([ADR 0038](../docs/adr/0038-host-usb-device-policy.md)) shows a blocked
device with its name, `vendor:product` id and port, and **Allow once** or
**Allow always** sends the allow on its way. What travelled was only the
port and the scope: `usb-allow 1-2 once` to the bridge, `usb:1-2:once` in
the operation record, `-e host_usb_allow_port=1-2` to the playbook.

Between the click and the root run there is the password prompt in the
operation window, which can take as long as the operator likes. If the
device shown is unplugged and another one, also blocked and also not a
keyboard or mouse, is plugged into the same port meanwhile, every check
still passes: the bridge sees a blocked non-HID device at that port, the
runner resolves the same command, and the playbook finds exactly one blocked
device at that `via-port` with no class 03 interface. The other device is
allowed, and with **Allow always** a USBGuard rule is written for it.

## Cause

The port was the only name the device had on its way. A port path names a
socket, not what is plugged into it. Each layer re-read the live state, as
designed, but compared it with nothing the operator had seen: the identity
shown on the card never left the shell.

## Fix

The device identity the operator saw, `vendor:product` in lowercase hex,
travels with the allow, and every layer checks it against what it reads now:

- the view passes the card's `vendor_id:product_id` to `allowUsb`, and
  disables the actions, with a reason, for a device whose ids cannot be
  read;
- `MachineActions` refuses an allow without a well-formed id and sends
  `usb-allow PORT SCOPE VVVV:PPPP`;
- the bridge refuses unless the device now at that port has exactly that id
  ("the device at that port is no longer the one shown");
- the operation target is `usb:PORT:SCOPE:VVVV:PPPP`; the runner refuses any
  other shape, passes the id to the registry, and still holds one allow per
  port whatever its scope or device;
- the registry action adds `-e host_usb_allow_device=VVVV:PPPP`, validated
  strictly;
- the playbook validates the id and, before `usbguard allow-device`, requires
  the single USBGuard line at that `via-port` to carry ` id VVVV:PPPP `; the
  refusal names the id expected and the id found;
- the tracker verifies the allow only when a fresh reading shows that same
  device authorized at that port.

USBGuard numbers a device anew at each insertion, so a device replaced after
the playbook's `usbguard list-devices` is not the one the id it passes to
`allow-device` names.

Two devices of the same model swapped on the same port still have the same
id; telling those apart would take the serial, which many devices do not
report. The id closes the case the review found: a different device.

## Regression proof

Each of these fails against the port-only code:

- the bridge contract refuses `usb-allow 1-2 once 1234:abcd` when the device
  at `1-2` is `0781:5581`, and refuses missing or malformed ids;
- the runner contract refuses `usb:1-2:once` and targets with a malformed id,
  and a record whose device was changed after launch does not run;
- the registry tests refuse a missing or malformed `usb_device`;
- the USBGuard contract requires the id check between the USBGuard listing
  and `allow-device`, and the device id among the validated inputs;
- the QML operation contract refuses `allowUsb` without a valid id, checks
  that the dispatched argv carries it, and that another device allowed at
  the same port does not verify the operation;
- the runtime scenario checks that **Allow once** passes the shown id and
  that a device without a readable id offers no allow.
