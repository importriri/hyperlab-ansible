# Operator paste block leaked strict shell mode into the interactive terminal

## Symptom

An operator command block enabled `set -euo pipefail` directly in the current
interactive shell. A later non-zero command therefore exited the terminal
instead of returning control to the operator.

## Root cause

Strict shell options are appropriate inside owned scripts and short-lived
subshells, but they are process state. Setting them in a paste block mutates the
operator's interactive shell for every command that follows.

## Fix

Interactive HyperLab procedures must not enable `errexit`, `nounset` or
`pipefail` in the caller shell.

When strict mode is useful, the procedure must put it inside a separate script,
`bash -c`, or a subshell whose lifetime is bounded by that operation.

## Proof

The interrupted Secure Boot recovery operation was inspected from a fresh
terminal. The recovery preview and checksum manifest had completed, the
accidental repository preview files were absent, EFI state was unchanged and
`git diff --check` remained clean.

## Status

Procedure corrected. Future operator snippets must preserve the caller's shell
state.
