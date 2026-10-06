# ADR 0050 - Hardware readiness and a host profile proposal, before install

Status: proposed.

## Context

HyperLab's host playbooks assume a computer that can run it: CPU
virtualization, an IOMMU, UEFI, a GPU the host keeps and, for a GPU Machine,
a second GPU alone in its IOMMU group. Today the only computers HyperLab
knows are the profiles in `group_vars/all/hardware.yml`, written by hand
(`nitro-3060`, `predator-3070`). An installer (C12, C13) needs to say before
it changes anything whether a computer is ready, and what its profile would
be.

## Options

**A. A read-only check that proposes a profile (recommended).**
`hyperlabctl doctor --hardware` reads `/proc` and `/sys` as the operator,
without privilege, and reports each readiness check as ok, warning or
failure, with what would clear it. `--profile NAME` prints a host profile in
the shape of `hardware.yml`: the passthrough GPU's vendor:device IDs,
pinning plans that keep each core's threads together, and the default
memory budget. The operator reviews it and adds it by hand.

**B. The installer writes the profile and uses it at once.** Faster, but a
profile decides which device leaves the host's control; HyperLab would then
trust what it read from the computer it is about to change, with no review.

**C. Root-level probing (lspci -vv, dmidecode, ACS capabilities).** More
detail, but it needs privilege before anything is installed, and nothing in
the profile needs it.

## Recommendation

A. A failure exits 2, so an installer can stop on it. The proposal names
itself a proposal and leaves the evidence fields (`gpu_pci`, `cpu_threads`)
null, as the reviewed profiles do until a preflight report is reviewed.

Rules the check keeps:

- the passthrough candidate is the display device the firmware did not boot
  on; there must be exactly one;
- its IOMMU group may hold only its own functions and PCI bridges. HyperLab
  never uses the ACS override: a shared group is reported, never split;
- the host keeps the boot GPU; a computer with one GPU still runs Machines,
  without a GPU of their own;
- pinning plans keep a core's threads together, run the emulator on the
  first core, give the I/O thread a second free core when one is left, and
  always leave the host one core.

## What this does not cover

- Whether the GPU resets cleanly after a Machine stops: that is seen only
  by running one (`reset_method` lists what the kernel would try, not
  whether it works).
- The keyboard layout: the proposal takes `/etc/vconsole.conf`, which on the
  Nitro says `us` while the desktop uses `it`. It is a value to review.
- Firmware settings that are not visible from Linux.

## Hardware test

On the Nitro, read-only, already run once on 2026-10-06:
`hyperlabctl doctor --hardware` reported every check ok, with
`0000:01:00.0 can be passed through alone (10de:2520, 10de:228e)`. Still to
do: the same on the Predator, and in the lab host (no passthrough GPU there,
so `gpu-passthrough` must be a warning and the exit 0).
