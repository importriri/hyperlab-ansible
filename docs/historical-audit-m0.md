# Historical audit: M0 baseline

State of the three repositories before any work on the VM factory, and the
decisions taken because of it. This linked archive is true only at the commits
below and is intentionally not a description of current `main`. The maintained
decisions are indexed in [`adr/README.md`](adr/README.md).

## Repositories at audit time

| Repository | Branch | Commit | Files | Suite |
|---|---|---|---|---|
| arch-bootstrap | main | `ff640a5` | 44 | bats 26/26 green |
| privatestack-ansible | main | `4358b88` | 79 | `verify.sh` all green |
| arch-hypervisor-lab | main | `f2e2312` | 32 | `verify_repo.py` OK |

All three working trees clean. Every suite was run unmodified before
anything was written.

## What the pipeline actually reaches

The three-stage split holds and the boundaries are not blurred.
`arch-bootstrap` produces an encrypted, Secure Boot host and stops.
`privatestack-ansible` turns it into a segmented hypervisor.
`arch-hypervisor-lab` records what was proven and what went wrong.

The level reached is **a configured host**: five libvirt networks, the
nftables drop matrix, four templated boot profiles, trust-ranked GPU
handoff, automatic laptop profile selection, the kvmfr transport and a
Looking Glass client pinned to a build.

The level not reached is **the VMs**. No code in any of the three
repositories creates, defines, starts or destroys a domain.

## Exists / partial / missing

| Area | State | Note |
|---|---|---|
| Encrypted base, Secure Boot, boot profiles | exists | |
| Hardware profile auto-selection | partial | `vfio_ids` only |
| Five network domains, isolation, reconciliation | exists | |
| Trust-ranked GPU handoff | exists | |
| kvmfr transport and pinned client | exists | host half; guest half manual by design |
| Sway cockpit, Emacs IDE | exists | opt-in |
| Image store, immutable bases | missing | `kvm_host` does not touch `/var/lib/libvirt` |
| Image manifests, checksums, import | missing | |
| `guest` brick, disposable/permanent, cloud-init | missing | README: planned, A8 |
| Per-VM NVRAM and TPM state, domain XML | missing | only a documentary fragment in the lab repo |
| Versioned VM specs | missing | |
| `hyperlabctl` | missing | |
| Speedrun timing, evidence bundle | missing | |
| The six images | missing | not even as a written procedure |

## Findings

**1. Two registries for the same PCI IDs.** `group_vars/all/hardware.yml`
and `arch-hypervisor-lab/hardware/compatibility.yml` both carry the
`vfio_ids` for both laptops. Nothing compares them. Resolved by
[ADR 0006](adr/0006-hardware-profile-source-of-truth.md).

**2. `tests/static_contract.py` never leaves its own repository** despite
being run under the heading "static cross-repository contract". It checks
contracts that *originate* elsewhere by reading the local copy, which is
useful and is not what the name claims.

**3. Memory is unbounded and undeclared.** The lab repository documents
that an 8 GB machine OOM-kills a 7 GB guest, because a PCI hostdev pins
the whole guest and makes ballooning ineffective. Nothing in the pipeline
knows this. Resolved by [ADR 0007](adr/0007-memory-budget-policy.md).

**4. Brick prerequisites are comments.** `playbooks/looking-glass.yml`
says to run `playbooks/host-desktop-sway.yml` first. Run in the wrong order it
still reports success and fails later, at the point where the client
cannot open `/dev/kvmfr0` because `TAG+="uaccess"` needs an active seat
session that does not exist. Resolved by
[ADR 0005](adr/0005-brick-prerequisites.md).

**5. `hardware_probe` cannot help you add a laptop.** On unknown hardware
it fails - correctly - but writes its report only *after* selecting a
profile, so the machine that most needs a report never gets one.

**6. Hardware profiles carry two fields.** The pipeline needs GPU and
audio PCI addresses, expected IOMMU groups, kernel quirks, CPU topology,
host memory reserve, kvmfr size and which iGPU the host keeps. Today it
has a label and two IDs.

## Implementation order

M0 is this file and the ADRs: decisions written down, nothing functional
changed. M1 turns the ADRs into contracts - schemas, the six manifests,
example specs, a validator, the extended hardware profiles and the brick
prerequisite graph - still with nothing destructive. Provisioning starts
at M3, after the image store exists at M2.

The order is deliberate: every milestone up to M3 can be verified on a
laptop that is doing something else at the time.
