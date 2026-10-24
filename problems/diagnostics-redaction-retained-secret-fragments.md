# Diagnostics and acceptance evidence retained fragments of secrets

## Failure

The diagnostics and acceptance redactors removed only the first word of
quoted password, passphrase and token assignments. The old test checked
that the entire original value disappeared, which missed surviving suffixes.
Diagnostics also truncated a source before redacting it: truncation could
remove a PEM opening marker while retaining its private body in the archive.

## Fix

The redactor consumes complete single- or double-quoted values, including
escaped quotes, and preserves the quoting around the replacement. Incomplete
PEM blocks are removed conservatively when an upstream tail has lost a marker.
Diagnostics redacts complete input before retaining its limited suffix.
Acceptance uses this same redactor, including its become-prompt protection,
rather than maintaining a second whitespace-based implementation.

## Regression evidence

Only synthetic values, keys, sources and temporary archives were used.
The expanded diagnostics suite initially reported 65 pass / 12 fail for
quoted values and an archive whose truncation cut a PEM header. It then
reported 77 pass / 0 fail. Additional incomplete-PEM cases reported
77 pass / 4 fail before their correction and 81 pass / 0 fail after it.
Assertions check each synthetic component, not just absence of the full value.

The acceptance contract executes its Bash evidence helper with synthetic
quoted values: the previous helper retained a suffix; the shared redactor
removes it. Collection tests replace operation records as well as command
outputs so they do not inspect the operator's records or any guest.
These are software regressions, not a full gate or hardware acceptance.
Existing archives have not been read or rewritten by this correction.
