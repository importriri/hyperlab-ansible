# Product identity readers disagreed at byte and path boundaries

Status: corrected in source and covered by shared isolated reader fixtures.
Physical presentation on Nitro and Predator remains pending.

## Symptom

The same identity file could produce different product names across shell,
CLI help and helper notifications. A lone trailing carriage return was
accepted by the CLI, accented names could be accepted by Bash in a language
locale, and the native shell followed redirected identity paths.

## Root cause

Python's text reader translated newlines before validating the document.
Bash regular-expression ranges used the caller's collation locale. QML's
FileView followed symlinks and exposed no check for the leaf or its parents.
Each reader's happy path worked, but their refusal fixtures were different.

## Fix

Use one fixture table across Python, every Bash reader and native Quickshell.
Python keeps original line endings. Bash sets a function-local C locale.
The native shell reads through the existing compositor adapter's fixed
`product-identity` route, using the same leaf/parent, file-type and
readable-mode checks as focus. The route accepts no caller path, works without
an active compositor and returns the original validated document bytes. QML still owns its identity grammar and publishes only after a
successful normal process exit. Failed transport, including failed startup,
leaves the identity empty. No operational command depends on this display
input; emergency-stop dispatch retains its independent contract.

The explicit readable-mode checks are intended to refuse zero-mode files when
an execution identity could otherwise read them. This is not verified here:
the unprivileged fixtures cannot establish root's runtime behavior. That remains
separate from the source checks and normal-user refusal cases.

## Regression proof

`tests/product_display_name_contract.py` uses the same byte/path cases for
all readers. It executes Bash under C and each installed UTF-8 locale,
including `en_US.utf8` where the accented-name failure was reproduced.
It requires a non-C UTF-8 locale and proves that an unguarded Bash range
actually accepts an accented word there. Discovery limited to C/C.utf8 fails
explicitly; otherwise the fixture could pass without exercising the defect.
Native Quickshell fixtures also inject a bridge that prints a valid document
and exits unsuccessfully, plus a missing bridge. Neither may publish
an identity. Restoring newline translation, locale dependence, symlink
following or failed-child publication fails the corresponding mutation. The existing
provenance contract still prohibits interpreters in shared QML.
