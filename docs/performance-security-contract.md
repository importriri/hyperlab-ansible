# Performance and security contract

HyperLab may optimize latency, frame pacing and throughput, but performance work
must not lower the security posture of the host.

The Nitro AN515-55 campaign uses the host as the security boundary and treats
the accelerated Arch guest as a performance-oriented workload inside that
boundary.

## Baseline

The reviewed Nitro baseline currently has:

- `linux-hardened` on the host;
- Intel IOMMU enabled with interrupt remapping;
- the RTX 3060 functions owned by `vfio-pci` on the host;
- KVM unsafe mappings disabled;
- CPU vulnerability mitigations enabled;
- ASLR and the managed hardening sysctls enabled;
- cgroup v2 with `cpuset`, `cpu`, `io` and `memory` controllers;
- a reviewed 4-vCPU topology using complete SMT sibling pairs;
- emulator and I/O thread affinity separated from guest vCPU affinity;
- Turbo enabled and Intel P-state EPP at `balance_performance`;
- no generic host tuning daemon competing with HyperLab policy.

This is the minimum security and ownership baseline for later measurements. A
benchmark performed below this baseline is not release evidence.

## Performance mode

A future HyperLab Gaming Mode may coordinate host and guest state.

Accepted candidate operations include:

- change host EPP to a reviewed performance policy while the workload runs;
- isolate reviewed guest CPU siblings from ordinary host scheduling;
- keep QEMU emulator and I/O work away from guest vCPU siblings;
- change reversible process and I/O priorities;
- reduce guest compositor effects;
- select reviewed NVIDIA performance behaviour;
- select a reviewed Nitro thermal/fan policy;
- start GameMode or MangoHud inside the guest;
- tune Looking Glass for measured latency or frame pacing;
- benchmark guest kernels, hugepage policies and reviewed vCPU plans.

Every temporary operation must be transactional: capture the previous value,
apply the requested state, validate it, and restore the captured value when the
workload exits or when the transition fails.

## Security floor

Performance mode must not:

- add `mitigations=off` or disable individual CPU vulnerability mitigations;
- disable split-lock mitigation as a performance shortcut;
- weaken IOMMU or VFIO isolation;
- enable unsafe KVM mappings;
- disable host ASLR or managed hardening sysctls;
- weaken Secure Boot state;
- weaken a future reviewed lockdown or module-enforcement policy;
- automatically overclock the passed-through GPU;
- mask virtualization in order to bypass an anti-cheat or platform policy.

Compatibility workarounds must remain explicit, narrow and documented. The
current host boot contract still carries `kvm.ignore_msrs=1`; that compatibility
relaxation is under review and must not be generalized into a performance
setting.

## Measurement policy

Changes are accepted from measurements, not from reputation or distribution
defaults. Relevant gaming comparisons record, when the workload permits:

- average FPS;
- 1% low;
- 0.1% low;
- p95 and p99 frame time;
- GPU utilization, clocks, power and temperature;
- CPU frequency and thermal behaviour;
- host responsiveness while Looking Glass is active.

The current reviewed 4-vCPU plan is the baseline. The existing 6-vCPU plan is a
candidate only: it becomes a performance profile only if measurements show that
its extra guest CPU capacity outweighs contention on the smaller host/QEMU
control plane.

CachyOS-derived ideas, alternate guest schedulers, hugepages and similar tuning
remain experiments until they beat the baseline without crossing the security
floor.

## Host and guest policy

The host remains hardened by default. Performance-oriented experiments belong
in the guest unless a host change has a clear, measured benefit and preserves
the host security boundary.

The golden image contains reusable tooling and policy, not game libraries,
large build artifacts or user data. Clone resource choices may exceed the
golden image resources when the reviewed hardware plan allows it.
