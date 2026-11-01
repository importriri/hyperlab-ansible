# The proposed emergency key was already bound

## What happened

ADR 0047 reserved the emergency key choice to the operator, but the host
Hyprland template registered SUPER+SHIFT+Escape to run
`hyperlabctl panic engage`. The host key sheet advertised it too. Installing
the configuration therefore enabled a proposal that cuts every running
domain's network links and pauses it. Sheet parity passed because the
binding and its advertised row agreed; parity alone cannot establish that
an action was authorized.

## Fix

Remove the proposed binding and its sheet row. The explicit CLI entrypoint,
record observation and confirmed Restore remain available. A later key
choice requires a separately authorized binding with its matching sheet
row. ADR 0047 remains Proposed and its physical campaign remains open.

## Regression proof

`tests/host_key_sheet_contract.py` renders the production Lua template with
independent fixture inputs and executes it under real Lua. Recording
dispatchers never run host commands. The contract rejects panic engagement
on any chord and requires the ordinary lock, key-sheet and clipboard
bindings to retain their destinations. Execution or syntax failure fails
the contract. Existing bidirectional parity checks remain in place, and
the real offscreen launcher rejects an emergency row while retaining its
ordinary rows and inert activation.

Each bound command is split into its simple commands, shell `-c` payloads
are split again, and the arguments after any `hyperlabctl` word go through
the real hyperlabctl parser, global options (`--json`, `--no-color`,
`--repo`) included. A first version compared the two words after
`hyperlabctl` literally, so `hyperlabctl --json panic engage`, the spelling
the project already uses elsewhere, or the same command inside `sh -c`
would have passed. A command reached only through a variable or a wrapper
script is still not seen.

The old binding and an alternate-chord binding both fail the executed
regression, as do global-option, interleaved-option, `sh`/`bash`/`dash`,
nested-shell and command-sequence spellings. Restoring only the old sheet row fails parity and the real QML
scenario. Removing or retargeting ordinary lock fails the positive control.
CLI fixture tests and the shell's emergency scenarios separately check
engagement, existing-record observation and exact, confirmed Restore.
