# Product identity was split between the deployed shell and CLI checkout

Status: corrected in source and covered by isolated operation fixtures.
Physical compositor and notification presentation remain pending.

## Symptom

An apply from a newer tree could leave QML showing the new name while focus
and notification helpers obtained an old banner from the CLI checkout. Focus
then found no matching window and notifications failed. Failed notifications
also turned already-successful appearance, layout and fallback-bar operations
into errors. Invalid product data could make the CLI print a traceback before
its normal refusal handler existed. Moving that read into parser construction
then blocked all commands, including emergency stop, on invalid display data.

## Root cause

The deployed QML product file and the CLI pointer can refer to different
revisions. Treating a CLI version banner as an installed identity transport
introduced a dependency on the Sway wrapper into the common compositor helper.
Notification failure then propagated through bare calls under `set -e` or
explicit `return 1`. The CLI read the display value during module import,
outside its `HyperlabError` boundary. Parser-time loading fixed the traceback
but still treated cosmetic identity as a prerequisite for command dispatch.

## Fix

Focus and the three notification helpers read the same installed product
file as QML, without invoking the CLI. Their bounded two-field readers reject
missing, unreadable, nonregular, redirected, duplicate and malformed inputs.
The maker byline is part of that shared document too. Owner PID, unique-match
and compositor identifier validation still constrain focus.

A withheld or undeliverable notification prints a diagnostic at its call
site without changing a completed operation's success. The CLI loads identity
only when formatting help or invoking its custom version action, inside the
normal error boundary. Invalid data refuses these displays with exit 2 and no
fallback name. Operational dispatch, including emergency stop, never reads
this cosmetic input. ADR 0058 records the distinction from policy inputs.

## Regression proof

The product contract executes focus and notification functions with a valid
deployed file and stale or failing CLI stubs. It runs the real keyboard
operation and theme/fallback-bar operation bodies with inert actuation,
checking saved layout, success, no notification and stderr diagnostics when
the product file is missing. The real CLI entry point is copied into an
isolated fixture to check missing, invalid, accented and redirected inputs:
help/version return exit 2, `hyperlabctl:` prefix and no traceback, while
`panic status` reads an isolated empty runtime directory successfully.
All four extracted Bash readers must match and refuse symlinked parents as
well as leaves. Source mutations restoring each defect
must fail the corresponding stage.
