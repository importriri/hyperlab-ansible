# The showcase name pattern checked three characters

## Failure

`tools/showcase/demo.sh` accepted Machine names such as `ab;id`, `ab cd`
and `aa.b`. They passed its name check and reached the preflight, the
inventory and, in a full take, `hyperlabctl open looking-glass`. The
contract only tried names that happened to fail on their first, second or
last character (`x;id` among them), so it stayed green.

## Cause and fix

The check was the shell pattern `[a-z][a-z0-9-]*[a-z0-9]`. In a `case`
pattern `*` is any string, not a repetition of the bracket before it, so
only three characters were checked and everything between them was
accepted. The script now also refuses any name containing a character
outside `a-z0-9-` (`*[!a-z0-9-]*`), keeps the 31-character limit, and
refuses a missing or extra argument. A refused name exits with status 2
before any tool runs.

## Regression proof

`tests/showcase_contract.py` runs the script with stub tools for each of
`x;id`, `ab;id`, `ab cd`, `aa.b`, `ab/cd`, `ab$x`, a name with a newline,
non-ASCII letters, a leading digit or dash, a trailing dash, one and 32
characters, no argument and two arguments. Each must exit with 2, print
only the usage line and leave every stub log empty. Without the new
refusal it fails with `name ['x;id']: exit status 1, not 2`.

This verifies software behavior with stub tools. It is not evidence of a
failure observed on the lab or on Nitro.
