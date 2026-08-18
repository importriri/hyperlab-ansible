# A chained Ansible gate could not reuse its become credential

Author: [importriri](https://github.com/importriri).

## Symptom

The rollback/reinstall acceptance wrapper stopped three times before its first
Ansible task could change the host.

The failures were different expressions of the same boundary:

1. `--ask-become-pass` could not recover from an initially mistyped password and
   aborted on the duplicate prompt;
2. a password validated with `sudo -v` was not available to Ansible's local
   become subprocess, which reported that a password was required;
3. a Bash process substitution was canonicalized from `/dev/fd/...` to a
   `/proc/.../pipe:[...]` target that Ansible rejected as missing.

All three attempts ended at `ok=0`, `changed=0`. The platform driver was never
partially removed by those failures.

## What was wrong

A sudo timestamp is not a portable credential handoff. Its scope may depend on
the terminal or process context, while Ansible creates its own become
subprocess.

Process substitution also does not behave like a stable password filename on
Linux because Ansible resolves symlinks before reading it. The resulting procfs
pipe description is not an openable path.

The wrapper needed one validated secret and a stable, private path for each of
three separate playbook processes without placing the secret in arguments or
long-lived files.

## Fix

The final evidence wrapper reads the password once with terminal echo disabled
and validates it before rollback begins.

For each Ansible invocation it creates a fresh FIFO with mode `0600` inside a
private runtime directory with mode `0700`. A short-lived writer feeds the
password to that FIFO, and Ansible receives the FIFO through
`--become-password-file`. The FIFO is unlinked after the invocation, and the
in-memory shell value is cleared after the final privileged run or on exit.

Nothing is placed in the command line or evidence archive.

## Regression evidence

The corrected gate completed the full transaction:

- rollback: `ok=46`, `changed=10`, `failed=0`;
- reinstall: `ok=113`, `changed=32`, `failed=0`;
- immediate second run: `ok=91`, `changed=0`, `failed=0`.

The rollback restored `acer_wmi` and removed the exact managed service, boot
policy, source, DKMS and ownership paths. The reinstall restored the pinned
module, build stamp, services and reviewed runtime values.

Chained hardware automation must validate authentication before its first
destructive step and must prove the exact credential path it will give Ansible.
An interactive sudo success in the parent shell is not enough.
