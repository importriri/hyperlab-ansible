# ADR 0013: Freeze storage ownership and evidence across repositories

- Status: accepted for M9 software validation
- Date: 2026-07-28

## Context

`arch-bootstrap` owns destructive disk selection, encryption, filesystems and
mounts. `privatestack-ansible` owns the Hyperlab directory and VM lifecycle.
Without an explicit hand-off, stage 2 could create valid VM paths on the wrong
physical disk while both repositories independently report success.

Hardware evidence also spans two repositories. Branch names are mutable, raw
logs can contain private data, and a successful Nitro run does not prove that a
later Predator run used identical software.

## Decision

Stage 1 writes `/etc/privatestack/bootstrap-storage.yml` only after observing
one of two supported mounted shapes:

- single disk: `/dev/mapper/cryptroot`, Btrfs filesystem root `/@vm`;
- dedicated VM disk: `/dev/mapper/cryptvm`, Btrfs filesystem root `/`.

The contract also binds the canonical mountpoint, subvolume identity, partlabels
and inherited NOCOW requirement. Stage 2 observes the live mount independently
and refuses before image-store writes unless declaration and observation agree.

A legacy Nitro installation may adopt only one already mounted supported shape.
Adoption writes the contract after exact confirmation and changes no storage.
Fresh Predator installations must receive the contract from the complete
bootstrap entrypoint.

The final campaign is generated from `release/acceptance.v1.yml` with exact
40-character SHA values for both repositories. Nitro runs first. Predator may
run only with the same frozen pair. Evidence sealing accepts only the complete
ordered gate matrix, scalar reviewed facts, hashes and short summaries. Raw logs
stay local and known sensitive patterns are refused.

## Consequences

- Hyperlab cannot silently land on root when a dedicated VM disk was declared.
- Stage 2 fails before directory, image or VM-state creation on storage drift.
- Existing Nitro data can be brought under the contract without remounting or
  moving it.
- Predator has no legacy bypass.
- Any software fix after Nitro creates a new two-repository freeze and requires
  Nitro repetition before Predator.
- Public evidence is reproducible by hashes but does not expose raw logs,
  credentials or private guest state.
- Merge remains a separate, explicitly authorized action.

## Rejected alternatives

- **Infer storage forever from `findmnt`:** cannot distinguish an intended
  topology from an accidental but currently mounted path.
- **Let Ansible create or repair mounts:** crosses the destructive ownership
  boundary and duplicates bootstrap logic.
- **Record branch names only:** branches are mutable and cannot prove identical
  Nitro/Predator software.
- **Publish complete command logs automatically:** risks credentials, home
  paths, private Windows evidence and other unrelated host data.
- **Run Predator before Nitro is stable:** makes the portability machine the
  first integration test for unfinished storage code.
