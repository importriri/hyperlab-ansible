# Final release and evidence campaign

M9 turns the stacked drafts into one ordered hardware campaign. It never merges,
pushes, publishes raw logs or authorizes a destructive action.

```text
freeze software
→ verify both repositories
→ test bootstrap and storage
→ reconcile the host twice
→ exercise VM, VFIO, Looking Glass and services
→ seal reviewed evidence
→ publish and merge deliberately
```

Nitro runs first. Predator may use only the same bootstrap and Ansible commits
that completed Nitro. Any change to either repository starts a new freeze and a
new Nitro campaign.

## 1. Create the private campaign workspace

The operator owns the files; root owns only the directory creation step:

```bash
RELEASE_DIR=/var/lib/privatestack/release
sudo install -d -m 0700 -o "$USER" -g "$(id -gn)" "$RELEASE_DIR"
```

Raw logs and mutable evidence stay here. They never enter Git automatically.

## 2. Freeze one published revision

Use exact 40-character commits from `main`. The acceptance manifest refuses
review branches, detached candidates and unpublished checkout names; the commit
identity remains the durable evidence key.

```bash
python tools/release_acceptance.py \
  --manifest release/acceptance.v1.yml \
  plan \
  --profile nitro-3060 \
  --campaign-id nitro-final-YYYYMMDD \
  --ansible-sha <M9-40-character-SHA> \
  --bootstrap-sha <bootstrap-40-character-SHA> \
  --output "$RELEASE_DIR/nitro-plan.json"

python tools/release_acceptance.py \
  --manifest release/acceptance.v1.yml \
  scaffold \
  --plan "$RELEASE_DIR/nitro-plan.json" \
  --output "$RELEASE_DIR/nitro-evidence.json"
```

Both files are mode `0600`. The plan is a canonical projection of the checked-in
manifest. Later commands refuse a modified contract, gate order, topology or
publication policy even when a plan file still parses.

## 3. Prove both checkouts

Keep the frozen repositories beside one another and refresh sudo credentials for
the bootstrap sparse-file LUKS header test:

```bash
sudo -v

python tools/release_acceptance.py \
  --manifest release/acceptance.v1.yml \
  repository-proof \
  --plan "$RELEASE_DIR/nitro-plan.json" \
  --ansible-repo "$PWD" \
  --bootstrap-repo "$PWD/../arch-bootstrap" \
  --log-dir "$RELEASE_DIR/nitro-local-logs" \
| python tools/release_acceptance.py \
    --manifest release/acceptance.v1.yml \
    record \
    --plan "$RELEASE_DIR/nitro-plan.json" \
    --evidence "$RELEASE_DIR/nitro-evidence.json" \
    --gate repository-software \
    --status pass \
    --summary 'Both frozen repositories passed their complete local verification.'
```

`repository-proof` requires exact HEAD, reviewed branch, expected GitHub origin,
a completely clean worktree and successful `bash verify.sh` in both repositories.
Raw transcripts stay local; the gate receives only a combined hash and commit
identity.

## 4. Build gate payloads without editing JSON

`tools/release_probe.py payload` accepts reviewed scalar values, booleans and
regular files. It computes hashes and refuses missing, extra, duplicate,
symlinked or mistyped fields.

Example for the bootstrap rehearsal:

```bash
python tools/release_probe.py \
  --manifest release/acceptance.v1.yml \
  payload \
  --gate bootstrap-dry-run \
  --hash-file dry_run_sha256="$RELEASE_DIR/bootstrap-dry-run.log" \
  --value selected_primary_disk=/dev/<root-disk> \
  --value selected_vm_disk=/dev/<vm-disk-or-none> \
  --true no_writes_observed \
| python tools/release_acceptance.py \
    --manifest release/acceptance.v1.yml \
    record \
    --plan "$RELEASE_DIR/nitro-plan.json" \
    --evidence "$RELEASE_DIR/nitro-evidence.json" \
    --gate bootstrap-dry-run \
    --status pass \
    --summary 'The reviewed bootstrap rehearsal selected the intended disks and made no writes.'
```

For a failed attempt, use `--status fail` with the exact same field contract. A
failed gate remains the next gate until a reviewed pass replaces it. A passed
gate is immutable.

## 5. Storage hand-off

A fresh installation must run the complete `arch-bootstrap/bootstrap` entrypoint.
Before the Hyperlab tree exists, stage 2 accepts only:

```text
single disk      cryptroot   fsroot /@vm
dedicated disk   cryptvm     fsroot /
mountpoint       /var/lib/libvirt/images
filesystem       Btrfs with inherited +C
```

The existing Nitro installation predates the contract. Its one permitted bridge
is non-destructive adoption of an already mounted supported shape:

```bash
ansible-playbook playbooks/bootstrap-storage-adopt.yml --check --diff

ansible-playbook playbooks/bootstrap-storage-adopt.yml --diff \
  -e bootstrap_storage_confirm_adopt='adopt:/var/lib/libvirt/images:<observed-mapper>'
```

Adoption writes only `/etc/privatestack/bootstrap-storage.yml` and validates it.
It never partitions, formats, mounts, remounts, moves or deletes data.

The reviewed Arch runtime identities live in `host_vars/localhost.yml`:
QEMU is `libvirt-qemu:libvirt-qemu` and swtpm is `tss:tss`. The KVM foundation
installs `swtpm` before the image-store gate. Retain the `getent` and traversal
results from the image-store run as the hardware proof; do not replace the
shared blocking sentinels or infer identities from commented `qemu.conf`
examples.

After `foundation.yml` creates the empty Hyperlab tree, record the live identity:

```bash
python tools/release_probe.py \
  --manifest release/acceptance.v1.yml \
  storage \
| python tools/release_acceptance.py \
    --manifest release/acceptance.v1.yml \
    record \
    --plan "$RELEASE_DIR/nitro-plan.json" \
    --evidence "$RELEASE_DIR/nitro-evidence.json" \
    --gate storage-handoff \
    --status pass \
    --summary 'The declared bootstrap topology matches the mounted Hyperlab store.'
```

The probe compares the root-owned contract, live mapper, Btrfs filesystem root,
`lsattr +C`, contract hash and the device backing the Hyperlab directory. When
the gate passes, the runner derives the top-level storage identity; later gates
cannot substitute another mapper or topology.

## 6. Host convergence

Retain the complete check, first apply and second apply logs:

```bash
ansible-playbook playbooks/lab.yml --check --diff \
  |& tee "$RELEASE_DIR/lab-check.log"
ansible-playbook playbooks/lab.yml \
  |& tee "$RELEASE_DIR/lab-first.log"
ansible-playbook playbooks/lab.yml \
  |& tee "$RELEASE_DIR/lab-second.log"
```

The idempotence probe parses the real `PLAY RECAP`. It refuses failed or
unreachable hosts and requires `changed=0` for every host on the second apply:

```bash
python tools/release_probe.py \
  --manifest release/acceptance.v1.yml \
  idempotence \
  --check-log "$RELEASE_DIR/lab-check.log" \
  --first-apply-log "$RELEASE_DIR/lab-first.log" \
  --second-apply-log "$RELEASE_DIR/lab-second.log" \
| python tools/release_acceptance.py \
    --manifest release/acceptance.v1.yml \
    record \
    --plan "$RELEASE_DIR/nitro-plan.json" \
    --evidence "$RELEASE_DIR/nitro-evidence.json" \
    --gate host-idempotence \
    --status pass \
    --summary 'The final laptop target converged and the second apply changed nothing.'
```

## 7. Remaining hardware gates

The checked-in order is:

```text
repository-software
bootstrap-dry-run
bootstrap-clean-install
storage-handoff
host-idempotence
network-isolation
standard-vm-lifecycle
vfio-trust-lifecycle
looking-glass
jellyfin-service
service-recovery
sanitized-publication
```

Use the generic payload probe for gates without a dedicated semantic collector:

```bash
python tools/release_probe.py \
  --manifest release/acceptance.v1.yml \
  payload \
  --gate <gate-id> \
  --hash-file <sha256-field>=<reviewed-local-file> \
  --value <scalar-field>=<reviewed-value> \
  --true <reviewed-boolean-field>
```

The output pipes directly into `release_acceptance.py record`. No evidence JSON
is assembled manually.

Raw logs remain local. Evidence contains only booleans, short reviewed identities,
hashes and summaries.

The PCIe freeze workaround is part of the reviewed VFIO profile. It was isolated
on Nitro through progressive parameter exclusion; Predator later reproduced the
same failure without it and confirmed the Nitro result within minutes. Routine
validation keeps `pcie_port_pm=off` instead of deliberately reintroducing a known
hard-freeze path.

## 8. Publication and sealing

Prepare and review the intended public report bundle first. The
`sanitized-publication` gate records `publication_bundle_sha256`, not the hash of
a receipt that does not exist yet. The final sealer creates that receipt after
all gates pass.

Check progress:

```bash
python tools/release_acceptance.py \
  --manifest release/acceptance.v1.yml \
  status \
  --plan "$RELEASE_DIR/nitro-plan.json" \
  --evidence "$RELEASE_DIR/nitro-evidence.json"
```

After `ready_to_seal: true`:

```bash
python tools/release_acceptance.py \
  --manifest release/acceptance.v1.yml \
  seal \
  --plan "$RELEASE_DIR/nitro-plan.json" \
  --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --output "$RELEASE_DIR/nitro-receipt.json"
```

The receipt binds canonical plan and evidence hashes, exact stage-1/stage-2
commits, storage topology and ordered gate IDs. It contains no raw logs and
performs no network publication.

## 9. Predator and merge order

Create the Predator plan only after the Nitro receipt exists. Use the same two
commit values and `--profile predator-3070`. Predator additionally proves the
dedicated-disk unlock/mount sequence and that all Hyperlab state is physically
on `cryptvm`.

A milestone is merged only after its documented hardware gate passes on its exact
head. Already validated lower milestones may merge while later stages remain
draft. A changed software head repeats the affected hardware gate before merge.

After both final receipts are reviewed:

1. publish sanitized evidence in `arch-hypervisor-lab`;
2. update compatibility status against exact commits;
3. merge the remaining Ansible milestones in order;
4. merge bootstrap and public documentation only after their cross-repository
   references match the verified identities.

A green CI run proves software contracts. Only the ordered Nitro and Predator
campaign proves physical compatibility.
