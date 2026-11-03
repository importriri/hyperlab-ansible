# The system panel did not link to the full host key sheet

## Observation

The Nitro capture session on 2026-11-02 found only SUPER+F and SUPER+O in
the shell's system panel. The full sheet already existed in `HostKeys.qml`,
reachable with SUPER+F1 or `qs -c hyperlab ipc call launcher keys`.

## Fix

The system panel now has an "All host shortcuts" row. It opens the existing
launcher in keys mode on the output that opened the panel; the shared
surface coordinator closes the panel. It adds no second shortcut list and
runs no host action. The row uses the same keyboard-accessible `PanelRow`
control as the rest of the panel.

## Regression proof and remaining gate

`tests/system_panel_key_sheet_contract.py` activates that row in the real
panel offscreen at large and small viewports, checks keys mode and output
ownership, and requires the existing sheet's rows without dispatching a
command. Removing the row fails. `tests/host_key_sheet_contract.py` retains
the two-way sheet/compositor parity check and the real launcher scenario.

On Nitro, open the system panel and activate All host shortcuts with the
pointer and keyboard. Compare it with SUPER+F1; both must open the same
searchable sheet. Physical focus and compositor interaction remain open.
