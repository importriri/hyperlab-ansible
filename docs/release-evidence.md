# Release evidence

Hardware evidence binds a result to exact repository commits. CI can reject a
bad software state, but it cannot certify a laptop it never ran on.

Nitro is the first hardware gate. Predator reuses the same frozen commits. If a
code change is needed for Predator, Nitro is reopened before the result is
published.

## Release line

The project publishes from `main`. There is no parallel release branch or PR
stack to reconcile later. Work is reviewed locally, hardware gates run against
the exact candidate commit, and publication is an explicit final action.

The three repositories keep separate jobs:

```text
arch-bootstrap      installs the encrypted base
hyperlab-ansible    configures the lab and owns workload transactions
arch-hypervisor-lab records sanitized hardware evidence
```

## 1. Freeze the candidate

Record exact 40-character commits for `hyperlab-ansible` and `arch-bootstrap`.
The acceptance plan stores those identities with the selected hardware profile.

Raw logs live outside Git under `/var/lib/privatestack/release`. That path is a
compatibility namespace used by the existing evidence tooling; it is not the
public repository name.

```bash
RELEASE_DIR=/var/lib/privatestack/release
sudo install -d -m 0700 -o "$USER" -g "$(id -gn)" "$RELEASE_DIR"

python tools/release_acceptance.py \
  --manifest release/acceptance.v2.yml \
  plan \
  --profile nitro-3060 \
  --campaign-id nitro-final-YYYYMMDD \
  --ansible-sha <HYPERLAB-ANSIBLE-SHA> \
  --bootstrap-sha <ARCH-BOOTSTRAP-SHA> \
  --output "$RELEASE_DIR/nitro-plan.json"

python tools/release_acceptance.py \
  --manifest release/acceptance.v2.yml \
  scaffold \
  --plan "$RELEASE_DIR/nitro-plan.json" \
  --output "$RELEASE_DIR/nitro-evidence.json"
```

The plan is a canonical projection of the checked-in manifest. A changed gate
order, repository identity or storage contract is refused instead of silently
being accepted as equivalent evidence.

The repository rename changes the repository identity carried by the receipt, so
this release uses acceptance schema v2. Old local v1 plans are rehearsal data;
regenerate the plan and scaffold instead of editing their repository keys by
hand.

## 2. Prove both software trees

The repository proof requires exact HEAD values, `main`, the reviewed GitHub
origins, clean worktrees and successful local verification in both repositories.

```bash
sudo -v

python tools/release_acceptance.py \
  --manifest release/acceptance.v2.yml \
  repository-proof \
  --plan "$RELEASE_DIR/nitro-plan.json" \
  --ansible-repo "$PWD" \
  --bootstrap-repo "$PWD/../arch-bootstrap" \
  --log-dir "$RELEASE_DIR/nitro-local-logs"
```

The command emits the payload for the `repository-software` gate. The raw
verification logs stay local; the evidence record keeps their digest and commit
identities.

## 3. Run the gates in order

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

A failed gate remains the next gate until it is replaced by a reviewed pass. A
passed gate is immutable. Do not edit the evidence JSON by hand to skip around a
failure.

For gates without a dedicated collector, build the payload from reviewed files
and scalar values:

```bash
python tools/release_probe.py \
  --manifest release/acceptance.v2.yml \
  payload \
  --gate <gate-id> \
  --hash-file <sha256-field>=<reviewed-local-file> \
  --value <scalar-field>=<reviewed-value> \
  --true <reviewed-boolean-field>
```

## 4. Storage hand-off

A fresh installation accepts only the storage shape written by
`arch-bootstrap`:

```text
single disk      cryptroot   fsroot /@vm
dedicated disk   cryptvm     fsroot /
mountpoint       /var/lib/libvirt/images
filesystem       Btrfs with inherited +C
```

The older `/etc/privatestack/bootstrap-storage.yml` path remains a compatibility
interface between the two repositories. Renaming the project does not justify
changing an already deployed storage contract without a versioned migration.

The storage probe compares that contract with the live mapper, Btrfs root,
`+C` state and the device backing the HyperLab image tree.

## 5. Host convergence

Keep the check-mode, first-apply and second-apply transcripts. The second real
apply must report `changed=0` for every host.

```bash
ansible-playbook -K playbooks/lab.yml --check --diff \
  |& tee "$RELEASE_DIR/lab-check.log"
ansible-playbook -K playbooks/lab.yml \
  |& tee "$RELEASE_DIR/lab-first.log"
ansible-playbook -K playbooks/lab.yml \
  |& tee "$RELEASE_DIR/lab-second.log"
```

Use `release_probe.py idempotence` to turn those transcripts into the typed gate
payload. A successful return code without a clean play recap is not enough.

## 6. Hardware gates

Nitro must prove the network policy, standard VM lifecycle, VFIO ownership,
Looking Glass path and service lifecycle on the frozen commits.

The known PCIe power-management workaround stays part of the reviewed Nitro
profile. Reintroducing a hard-freeze condition is not a useful routine test.

For the current Linux VFIO guest, distinguish demonstrated video transport from
still-open persistence/input work. Do not mark the Looking Glass gate complete
until the release manifest's evidence fields and the current runbook agree with
what was actually observed.

## 7. Sanitize and seal

Public evidence contains hashes, short reviewed identities, booleans and concise
summaries. Raw terminal logs, home-directory paths, credentials, private keys,
account details and guest image contents stay local.

Check progress with `status`. Seal only when the runner reports that every gate
is ready. The receipt binds the plan and evidence hashes, repository commits,
storage topology and ordered gate IDs; sealing does not publish anything.

## 8. Publish Nitro, then replay Predator

After the Nitro receipt is reviewed:

1. add only sanitized evidence to `arch-hypervisor-lab`;
2. update its compatibility record against the exact commits;
3. commit and push each reviewed repository deliberately on `main`;
4. create the Predator plan with those same commit identities;
5. replay the complete hardware path on Predator.

A Predator-only code change creates a new candidate. It is not evidence for the
already frozen Nitro result until Nitro is rerun against that new candidate.
