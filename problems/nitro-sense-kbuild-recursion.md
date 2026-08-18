# A manual Kbuild invocation replaced the probe Makefile and recursed

Author: [importriri](https://github.com/importriri).

## Symptom

A temporary Linuwu-Sense build probe entered a rapidly growing recursive
`make` chain, reaching hundreds of nested invocations before it was interrupted.

The managed source checkout, installed DKMS module and running platform driver
were not involved.

## What was wrong

The probe was no longer being built through the role's deterministic wrapper.
A direct kernel-style invocation had caused Kbuild to generate a wrapper
Makefile inside the temporary probe. Reusing that generated file as though it
were the role recipe made the build call back into itself.

The failure was caused by mixing two build entry points in one temporary tree,
not by the Linuwu-Sense source change.

## Fix

Restore the probe Makefile from `roles/nitro_sense/templates/Makefile.j2` and
use the same entry point as the Ansible role:

```text
make -j<N> KVER=<running-kernel>
```

That wrapper is the only supported probe entry point. It delegates once to the
running kernel build tree with the probe directory as `M=`.

Temporary experiments must not reuse a Kbuild-generated Makefile as repository
input.

## Regression proof

After restoring the role recipe, the exact role-style build completed against
`7.1.8-hardened1-2-hardened` and produced a non-empty `linuwu_sense.ko` with the
expected vermagic.

The remaining modpost warning about writable function pointers came from the
kernel build checks and did not reproduce the recursive build failure.
