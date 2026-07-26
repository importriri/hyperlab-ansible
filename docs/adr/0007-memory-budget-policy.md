# ADR 0007 - Memory is a budget computed at run time, never a literal

## Context

The two target laptops have 8 GB and 16 GB today and both go to 32 GB
within a couple of months. The lab repository already documents the
failure mode: on an 8 GB machine a 7 GB guest is killed by the OOM
killer, because a PCI hostdev pins the whole guest and makes ballooning
ineffective.

A spec that says `memory_mb: 12288` is therefore correct on one laptop,
fatal on another, and wastefully small on both after the upgrade.

The naive budget - total minus a host reserve - is wrong in four ways
that only show up on a machine that is already doing something:

- QEMU costs memory *outside* the guest's own allocation: the emulator
  process, vhost rings, the video and shared-memory backends. On a VFIO
  guest the kvmfr window alone is a fixed, non-negotiable slice.
- Another VM may already be running. A budget that ignores it hands out
  the same megabytes twice.
- Some memory is spoken for even when idle: the service VMs that are
  expected to always fit are not free capacity.
- Ballooning works on a `standard` guest and does not work on a `vfio`
  one. One overcommit policy cannot be correct for both.

## Decision

### Two checks, not one

**Static capacity check** runs offline, in CI, with no host: it never
computes fit, because total memory is unknown. It verifies internal
consistency only - an explicit `memory_mb` is at or above the image's
`min_memory_mb`; an `auto` request has a `max_auto_memory_mb` ceiling
that is itself at or above that floor; a `vfio` spec does not request
overcommit. A green static check does not mean the VM will start.

**Runtime fit check** runs on the host, against facts and libvirt, at
the moment of creation or start. It is the only thing allowed to say
yes.

### The budget

```
available_mb = memtotal_mb
             - host_reserved_mb          (per hardware profile)
             - hypervisor_overhead_mb    (per hardware profile)
             - services_reserved_mb      (per hardware profile)
             - sum(allocated memory of every running domain)
             - vfio_fixed_overhead_mb    (vfio profile only: kvmfr window
                                          plus the pinned-guest margin)
```

`host_reserved_mb` covers the OS, page cache and the cockpit when it is
mounted. `hypervisor_overhead_mb` covers per-VM QEMU cost. Both are
declared by the hardware profile; neither declares a total, so the RAM
upgrade needs no file edit.

Running domains are read from libvirt, not remembered. State that is
derived and cached is state that is wrong.

### auto, and its ceiling

```
memory_mb: auto  ->  min(available_mb, max_auto_memory_mb)
                     rounded down to a multiple of 1024
```

`max_auto_memory_mb` is declared per hardware profile and exists so a
32 GB laptop does not hand 28 GB to a Windows guest that has no use for
it. Without a ceiling, `auto` is a request for everything, which is a
different and much worse default.

The result must still clear `image.min_memory_mb`. Below it, the check
fails closed with every number in the message: total, each deduction,
what was left, and what the image needed.

### Overcommit is explicit and profile-dependent

`hyperlab_memory_overcommit_ratio`, default `1.0`, meaning none: the sum
of guest allocations may not exceed `available_mb`.

- On `standard`, a value above 1.0 is honoured. Ballooning and swap make
  it survivable, and the operator asked for it.
- On `vfio`, it is **ignored and refused**. A hostdev pins the whole
  allocation; there is nothing to reclaim and no swap path that ends
  well. A `vfio` spec that requests overcommit fails the static check,
  not the runtime one, so it never reaches a host.
- Any ratio above 1.0 is also refused while a VFIO domain is running,
  whatever the profile of the VM being started.

## Consequences

- The 8 to 32 GB upgrade needs zero file edits. An `auto` spec grows by
  itself up to its ceiling; an explicit one keeps working.
- `win11clean-valley` on the 8 GB laptop fails at validation, in a
  message that names the shortfall, instead of at the OOM killer five
  minutes into a boot. The same file becomes a pass by itself when the
  RAM arrives.
- CI can validate every spec without a hypervisor, and cannot pretend it
  validated fit.
- "One VFIO VM at a time" gains a second, independent reason to be true,
  and the runtime check enforces it with arithmetic rather than a rule.
- Hugepages stay out of the default path: a static reservation is the
  opposite of a budget.
