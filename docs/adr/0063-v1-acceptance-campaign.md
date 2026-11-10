# ADR 0063 - Qualify the selected v1 with a separate acceptance campaign

Status: Proposed

## Context

The historical `release/acceptance.v2.yml` requires Jellyfin and service
recovery but cannot record the selected v1's server SSH, shell creation,
disposable lifecycle, GPU lease or Showcase. A v2 receipt cannot qualify v1.
Design acceptance, software fixtures, nested host convergence and physical
observations are separate evidence levels.

## Decision

Use `release/acceptance.v3.yml` for the selected v1. Manifest, canonical plan,
scaffold, evidence and receipt all carry integer `schema_version: 3`.
Explicit v2 selection retains the historical campaign and its strict boolean,
ordering, privacy and immutability rules. Unsupported and mixed versions
refuse without rewriting inputs or producing a receipt. No campaign upgrade,
pass import or automatic migration exists. Prior observations, including the
operator-observed, unpublished observations of 3–8 November 2026 at
`1e42308a863180590fc9b2a209b41227978b8a4f`, must be repeated on the frozen
commits; they cannot be imported as campaign passes.

Both profiles use exactly this gate order. Nitro runs first; Predator uses
its own pending scaffold at the same two frozen automation commits.
V1 requires reviewed runnable clean GPU and dirty/lab fixtures; qualification
without those fixtures is ruled out by this proposal.

| Order | Gate | Selected requirement and evidence boundary |
| --- | --- | --- |
| 10 | `repository-software` | Exact clean commits and verification digest for both automation repositories. |
| 20 | `bootstrap-dry-run` | Explicit primary/VM disk choices, log hash and no writes observed. |
| 30 | `bootstrap-clean-install` | Fresh encrypted installation, two hardened boots, Secure Boot state and networking. |
| 40 | `storage-handoff` | Independent mapper, filesystem root, Btrfs NOCOW and HyperLab-device comparison. |
| 50 | `host-idempotence` | Check/diff, first apply and unchanged second apply of `playbooks/v1-host.yml`. |
| 60 | `network-isolation` | Persistent network identities, active networks, cross-domain and isolated-lab refusals. |
| 70 | `standard-vm-lifecycle` | Reviewed create, validate, start, shutdown and confirmed destroy. |
| 80 | `vfio-clean-baseline` | PCI/IOMMU identity, real clean GPU use and shutdown before any dev GPU use. |
| 90 | `server-ssh` | Independent Debian and Fedora strict SSH and restricted-agent observations, with separate log hashes (milestone 4). |
| 100 | `shell-creation` | Permanent server and workstation creation through the shell, separate durable operations, terminal-only secrets, window-close survival, duplicate refusal and the ADR 0053 refusal observations (milestone 5). |
| 110 | `disposable-lifecycle` | Independent normal-stop, forced-stop and Power Cycle write discard, temporary-overlay removal, restricted agent, refreshed pin and strict SSH; unchanged sealed base (milestone 5). |
| 120 | `looking-glass` | Real shared-memory video, host/guest builds, kvmfr identity and private per-domain SPICE socket (milestone 1). |
| 130 | `workstation-access` | PRIMARY pre-login recovery and automatic LG handoff; keyboard/pointer capture, RightCtrl release, SUPER isolation, guest shortcuts and lock, reconnect/logout recovery, host frames in window and fullscreen (milestone 1). |
| 140 | `physical-audio` | Audible guest output without clipping, host volume cap and no guest microphone (milestone 1). |
| 150 | `gpu-lease` | `workstation-dev-standard`, default boot without GPU; real GPU → without GPU → GPU runs in one host boot, LG on GPU runs, SPICE without GPU, host-owned lease and unchanged ladder on the GPU-less run (milestone 5b). |
| 160 | `showcase` | Complete storyboard including shell creation, real lease, LG/Desks, host provenance, honest captions and manual frame privacy review, bound to the recording hash. |
| 170 | `vfio-trust-lifecycle` | Exclusive owner and downward dirty/lab transitions; separate clean-after-dev, dev-after-dirty, upward-after-lab and unmapped-PCI refusals; reboot resets trust. |
| 180 | `session-recovery` | Guest reboot and agent reconnect, host reboot, cold start, encrypted storage, separate PRIMARY/input/audio recovery, Sway/console recovery, guest profile changed=0 and disposable crash recovery. |
| 190 | `sanitized-publication` | Reviewed bundle digest, exact commit matrix, known limits and no sensitive patterns. |

The scalar field list in the manifest makes each outcome independently
representable. `server-ssh` cannot substitute Fedora for Debian; normal stop
cannot substitute for forced stop or crash. Every observation boolean must
be exactly true for a pass. A failed gate may retain false and prevents
sealing. Hashes remain lowercase SHA-256; descriptive fields retain the
existing scalar validation. `lease_template` must be exactly
`workstation-dev-standard`. No single success field replaces these facts.
`lease_runs_same_host_boot` observes that all three lease runs share one host
boot; retain the boot identity with each run in the hashed lease transcript.
`clean_after_dev_refused`, `dev_after_dirty_refused`, `upward_after_lab_refused`
and `unmapped_pci_refused` record the corresponding policy refusals separately
from the descriptive downward-transition log. An absent fixture cannot make
any refusal boolean true.

Accepted decisions map as follows:

- [ADR 0017](0017-shell-machine-creation.md): `shell-creation`, with separate
  server/workstation creation and durable-operation observations.
- [ADR 0018](0018-disposable-discards-on-stop.md): `disposable-lifecycle`,
  including the restricted agent and refreshed pin after every managed boot;
  destructive host-crash outcomes are separate in `session-recovery`.
- [ADR 0019](0019-gpu-lease.md): `gpu-lease`, initially only the selected
  Template, default without GPU; no change to the trust ladder.
- [ADR 0053](0053-withdraw-machine-intent.md): `shell-creation` requires both
  refused creation leaving no record and refusal to withdraw a live domain.
  This records observations, not a broader cleanup guarantee.

Jellyfin and service recovery belong to a subsequent phase and are not v1
requirements. Their historical v2 gates remain intact. The complete allowed
storage topology mappings are identical in v2 and v3; the existing bootstrap
v2 comparison plus that equality proves storage agreement only.

## Observation order and prerequisites

Pure fixtures verify schema, CLI refusals and deterministic hashes. A nested
lab may verify software application and convergence; neither counts as
Nitro or Predator acceptance. Every real campaign begins pending, even when
all fixtures pass.

Install and the two initial hardened boots interrupt the session before host
and guest work. Clean GPU use precedes dev use; dev work, lease and the full
Showcase precede dirty/lab transitions. Shut down all GPU owners between
Machines. `vfio-trust-lifecycle` records the descent and its subsequent host
reboot reset; recovery continues in the new boot. Never raise the ladder in
the same boot or edit its state to continue a take. Recovery's cold start
and disposable host-crash test are distinct from a clean shutdown.

The following remain prerequisites, not evidence or invented commands:

- `debian-server` must be prepared and sealed, and `server-debian` made
  ready before its SSH or Create observation.
- The disposable access amendment is implemented in software: recreate a
  throwaway Machine with a fresh seed containing the restriction, then
  observe normal/forced stops and pin refresh on the frozen commits.
  Existing seeds are not upgraded by a host apply. Hardware passes remain
  pending until that access path and the discard tests are accepted.
- `workstation-dev-standard` needs a sealed image with a session in both
  shapes and readiness, followed by Create acceptance and real lease
  controls. The lease controls are not implemented; no lease CLI is prescribed.
- Ladder tests require reviewed runnable clean, dirty, lab and unmapped PCI
  fixtures; an absent image is not a policy refusal.
- PRIMARY/input/audio observations, the complete recording and every-frame
  privacy review are pending. The current demo's lease placeholder is not
  a complete lease shot.
- Portable Predator display/input/audio/lease checks are pending. A
  Nitro-specific checker cannot certify Predator.

## Consequences

The manifest can describe an unfinished campaign without passing it. The
runner is a local evidence recorder, not an observer, publisher or signature
service. A receipt binds supplied facts and hashes; it neither authenticates
observations nor grants a release claim. Manual privacy review remains
necessary even when pattern checks pass. No product path is implemented by
adding these fields.

The independent oracle in `tests/release_acceptance_contract.py` enumerates
both gate lists and every field class. It compares the v3 ADR table,
manifest and fixture plan, and exercises the real CLI for both profiles.
The [runbook](../release-evidence.md) separates synthetic rehearsal from
physical use. Release qualification and all physical roadmap boxes remain
open.
