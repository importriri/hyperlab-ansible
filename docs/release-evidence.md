# Release evidence

The selected v1 uses [`acceptance.v3.yml`](../release/acceptance.v3.yml)
(schema version 3), proposed in [ADR 0063](adr/0063-v1-acceptance-campaign.md).
Nitro runs first; Predator repeats the same frozen pair of automation commits
in a separate campaign. Software fixtures and nested-lab convergence do not
qualify either laptop.

The unchanged [`acceptance.v2.yml`](../release/acceptance.v2.yml) is the
explicit historical campaign, including Jellyfin and service recovery.
`--manifest release/acceptance.v2.yml` retains that behavior and strictness;
a v2 receipt cannot qualify the selected v1. Every command below selects v3.
Unsupported or mixed manifest/plan/evidence versions refuse without rewriting
inputs or creating a receipt. There is no upgrade or pass-import command.
Observations from 3–8 November 2026 at `1e42308` are operator-observed,
unpublished; repeat them on the frozen commits rather than importing them.

The repositories have separate roles: `arch-bootstrap` installs the encrypted
base, `hyperlab-ansible` owns host/workload transactions, and
`arch-hypervisor-lab` receives reviewed sanitized evidence. Integration work
continues on `main`; a hardware campaign freezes exact public `main` commits.
Any automation change after the freeze requires a new candidate and Nitro
repetition before Predator.

## 1. Freeze the candidate

Only after software prerequisites are accepted, select the actual 40-character
commits and a new campaign id. Prepare a private writable directory outside
Git, mode 0700, for local logs. The existing operator location is
`/var/lib/privatestack/release`; its compatibility name is unchanged. Set
`RELEASE_DIR`, `CAMPAIGN_ID`, `ANSIBLE_SHA` and `BOOTSTRAP_SHA` to the reviewed real values.
These commands do not freeze the current checkout implicitly:

```bash
python tools/release_acceptance.py --manifest release/acceptance.v3.yml plan \
  --profile nitro-3060 --campaign-id "${CAMPAIGN_ID:?new lowercase campaign id}" \
  --ansible-sha "${ANSIBLE_SHA:?exact public commit}" \
  --bootstrap-sha "${BOOTSTRAP_SHA:?exact public commit}" \
  --output "${RELEASE_DIR:?private directory}/nitro-plan.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml scaffold \
  --plan "$RELEASE_DIR/nitro-plan.json" --output "$RELEASE_DIR/nitro-evidence.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml status \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json"
```

The plan is the exact canonical manifest projection. Scaffold creates mode-0600
evidence with all 19 gates pending, all observations null, storage null and
sanitized false. Status reports `passed: 0`, `total: 19`,
`next_gate: repository-software`, `failed_gates: []`, `ready_to_seal: false`.
Sealing this scaffold must exit 2 and write no receipt. Do not edit campaign
JSON or fill unobserved passes to get past a pending prerequisite.

## 2. Prove both software trees

The repository proof requires exact HEAD values, `main`, reviewed origins,
clean worktrees and successful verification in both repositories. Arrange
render credentials through the existing verification workflow before the
physical campaign; an incomplete render check is not a software pass.

```bash
python tools/release_acceptance.py --manifest release/acceptance.v3.yml repository-proof \
  --plan "$RELEASE_DIR/nitro-plan.json" --ansible-repo "$PWD" \
  --bootstrap-repo "$PWD/../arch-bootstrap" --log-dir "$RELEASE_DIR/nitro-local-logs" \
  > "$RELEASE_DIR/repository-software.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml record \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --gate repository-software --status pass --summary "Reviewed exact software pair" \
  < "$RELEASE_DIR/repository-software.json"
```

Raw logs stay local. The payload stores only their combined digest, clean-tree
observation and exact commits. A failed command produces no acceptable payload.
Run each command only after the previous one succeeds.

## 3. Run the gates in order

```text
repository-software
bootstrap-dry-run
bootstrap-clean-install
storage-handoff
host-idempotence
network-isolation
standard-vm-lifecycle
vfio-clean-baseline
server-ssh
shell-creation
disposable-lifecycle
looking-glass
workstation-access
physical-audio
gpu-lease
showcase
vfio-trust-lifecycle
session-recovery
sanitized-publication
```

The [ADR's gate table](adr/0063-v1-acceptance-campaign.md) maps the phase-1
requirements to these observations. The manifest lists each required scalar.
For both versions, booleans use JSON `true`/`false` only, SHA-256 fields use
64 lowercase hex characters, and descriptive values are scalars, never nested
logs. Use short reviewed text for descriptions. `lease_template` is exactly
`workstation-dev-standard`. Hashes identify reviewed local files; they do not
prove their contents. No field is a catch-all pass for an omitted observation.

Use `--true FIELD` or `--false FIELD` for observations. `--value` refuses
boolean fields; strings `"true"`, `"false"` and integers 0/1 are refused by
record in both passed and failed gates. Every observation must be true to
record a pass. A false observation belongs in a failed gate, which stays the
next gate and prevents sealing. Passed gates are immutable. `status` and
`seal` also refuse an edited false pass. Duplicate keys, missing/unreadable
files and redirected campaign inputs are refused.

For example, only after independently observing both distributions, make the
complete server payload (the two files must contain the actual reviewed
observations, not fixture output):

```bash
python tools/release_probe.py --manifest release/acceptance.v3.yml payload \
  --gate server-ssh --hash-file "debian_ssh_sha256=$RELEASE_DIR/debian-ssh.log" \
  --hash-file "fedora_ssh_sha256=$RELEASE_DIR/fedora-ssh.log" \
  --true debian_strict_ssh --true fedora_strict_ssh \
  --true debian_agent_restricted --true fedora_agent_restricted \
  > "$RELEASE_DIR/server-ssh.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml record \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --gate server-ssh --status pass --summary "Both servers observed with strict SSH and restricted agent" \
  < "$RELEASE_DIR/server-ssh.json"
```

If Debian is not observed, leave the gate pending. If it is observed failing,
use `--false debian_strict_ssh` and `--status fail`, retaining the other actual
facts. Do not record a pass to reach a later gate. Other payloads use the same
commands with their exact gate id and complete field list from the manifest.

## 4. Storage hand-off

Both versions have exactly the same complete topology mapping: single disk is
`cryptroot`, filesystem root `/@vm`, subvolume `@vm`; dedicated disk is
`cryptvm`, root `/`, null subvolume. Both use Btrfs, inherited NOCOW and
`/var/lib/libvirt/images`. The existing compatibility contract is
`/etc/privatestack/bootstrap-storage.yml`.

```bash
python tools/release_probe.py --manifest release/acceptance.v3.yml storage \
  --contract /etc/privatestack/bootstrap-storage.yml \
  --mountpoint /var/lib/libvirt/images --hyperlab-root /var/lib/libvirt/images/hyperlab \
  > "$RELEASE_DIR/storage-handoff.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml record \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --gate storage-handoff --status pass --summary "Observed bootstrap storage hand-off" \
  < "$RELEASE_DIR/storage-handoff.json"
```

The probe compares the actual contract, mount observations, NOCOW and the device
backing the HyperLab store. Software proof runs the unchanged bootstrap
required-mode verifier against this checkout, with bytecode writes disabled.
Its v2 comparison plus independently tested v2/v3 mapping equality proves
storage agreement, not v1 runtime qualification or a physical mount.

## 5. Host convergence

The gate measures `playbooks/v1-host.yml`: `lab.yml`, managed Hyprland and
Quickshell staged beside Sway recovery, and the VFIO sleep guard. All three
transcripts must run that target. The second real apply requires `changed=0`,
`failed=0` and `unreachable=0` for every host, including desktop changes.
These commands are physical operator transactions, outside the synthetic
rehearsal:

```bash
set -o pipefail
ansible-playbook -K playbooks/v1-host.yml --check --diff \
  |& tee "$RELEASE_DIR/v1-host-check.log"
ansible-playbook -K playbooks/v1-host.yml \
  |& tee "$RELEASE_DIR/v1-host-first.log"
ansible-playbook -K playbooks/v1-host.yml \
  |& tee "$RELEASE_DIR/v1-host-second.log"
```

Require successful commands as well as clean recaps; use shell pipefail when
capturing logs. USBGuard, QEMU AppArmor, measured boot, the security plane and
Nitro thermal control remain outside this target's convergence claim.

```bash
python tools/release_probe.py --manifest release/acceptance.v3.yml idempotence \
  --check-log "$RELEASE_DIR/v1-host-check.log" --first-apply-log "$RELEASE_DIR/v1-host-first.log" \
  --second-apply-log "$RELEASE_DIR/v1-host-second.log" > "$RELEASE_DIR/host-idempotence.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml record \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --gate host-idempotence --status pass --summary "Same host target converged unchanged" \
  < "$RELEASE_DIR/host-idempotence.json"
```

## 6. Physical observations and pending prerequisites

Installation and the first two hardened boots precede the guest session.
Prove clean GPU use before any dev GPU use. Finish server/Create/disposable,
PRIMARY, input/audio, lease and the full Showcase before dirty/lab tests.
Stop the current GPU owner before starting another. Dirty/lab lowers trust;
a host reboot is required before later dev recovery. Never edit ladder state
to regain a higher rung. Observe the reset for `vfio-trust-lifecycle` after
that reboot, then continue `session-recovery` in the new boot. Guest reboot,
host reboot, physical cold start and disposable host-crash recovery are
separate outcomes. Use an isolated, prepared disposable environment for the
crash observation; a clean shutdown does not prove crash cleanup.

Keep the reviewed Nitro PCIe power workaround; deliberately recreating a known
freeze is not a routine gate. Physical audio requires actual listening; XML,
codec state or a log cannot prove audibility. PRIMARY needs pre-login recovery,
automatic handoff to real LG video and input isolation, including reconnect,
lock and release. A SPICE image does not prove Looking Glass shared-memory
video. Use the observed private per-domain Unix socket, not the static TCP
client fallback, for `spice_socket_path`.

Prerequisites remain explicit:

- **Debian:** `debian-server` prepared/sealed and `server-debian` ready;
  Fedora readiness cannot stand in for Debian SSH.
- **Create:** accepted installed shell/provisioner and fresh throwaway server
  and workstation Machines, through durable operations. Observe ADR 0053's
  refused intent leaving no record and live-domain withdrawal refusal on
  dedicated test state; software tests alone do not fill these booleans.
- **Disposable:** the access amendment now has software coverage, including
  the full restricted-agent policy and refreshed pin. A fresh seed is required;
  host application does not rewrite existing seeds. Physical normal/forced
  stop, Power Cycle and crash observations remain pending on the frozen code.
- **Lease:** `workstation-dev-standard` captured/sealed and ready for both
  shapes, Create accepted, then real lease controls implemented and reviewed.
  Default boot is without GPU. Observe GPU → without GPU → GPU in one boot,
  record `lease_runs_same_host_boot` and retain the host boot identity for each
  run in the hashed lease log, with unchanged ladder during the GPU-less run.
  No lease CLI exists yet; obtain its actual controls from that implementation
  before proceeding.
- **Ladder:** reviewed runnable clean/dirty/lab and unmapped PCI test fixtures;
  this proposal requires them before qualification. Record the separate
  `clean_after_dev_refused`, `dev_after_dirty_refused`, `upward_after_lab_refused`
  and `unmapped_pci_refused` observations. After lab, observe refusal of starts
  at every higher trust level. A missing image/domain is not a security refusal.
- **Showcase:** a complete recording, including the real lease, honest editing
  and captions, and manual review of every frame with text. The current
  storyboard's lease placeholder cannot qualify as a complete take. Follow
  [the storyboard and privacy list](showcase.md); a clean transcript cannot
  certify the other windows, notifications or pixels.
- **Predator:** portable display/input/audio/lease checks are pending. The
  Nitro-specific host checker is not a Predator acceptance command.

Missing prerequisites leave gates pending. This tooling change implements none
of those product paths and grants no physical pass.

## 7. Sanitize and seal

Manually approve the publication bundle before hashing it. Retain raw logs,
images, home/runtime paths, credentials, keys and unreviewed screenshots only
in private local storage. Pattern checks supplement manual review. Use the
exact pair and honest known limits in the descriptive scalars.

```bash
python tools/release_probe.py --manifest release/acceptance.v3.yml payload \
  --gate sanitized-publication \
  --hash-file "publication_bundle_sha256=$RELEASE_DIR/publication-bundle" \
  --true no_sensitive_patterns \
  --value "exact_commit_matrix=hyperlab_ansible=$ANSIBLE_SHA;arch_bootstrap=$BOOTSTRAP_SHA" \
  --value "known_limits=Reviewed limits in the approved bundle" > "$RELEASE_DIR/sanitized-publication.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml record \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --gate sanitized-publication --status pass --summary "Manually reviewed sanitized bundle" \
  < "$RELEASE_DIR/sanitized-publication.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml status \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json"
python tools/release_acceptance.py --manifest release/acceptance.v3.yml seal \
  --plan "$RELEASE_DIR/nitro-plan.json" --evidence "$RELEASE_DIR/nitro-evidence.json" \
  --output "$RELEASE_DIR/nitro-receipt.json"
```

Only seal after status reports 19/19 passed, no failures, null next gate and
`ready_to_seal: true`. A refused seal exits 2 and creates no receipt. Sealing
is local: it binds hashes, ordered gates, profile, storage and commits. It does
not publish, sign or authenticate observations. Only actual operator evidence
can make a real campaign ready.

## 8. Review Nitro, then replay Predator

After reviewing Nitro evidence, the operator separately decides publication
in `arch-hypervisor-lab`. Its evidence commit may advance; the two automation
commits must stay frozen. Create a new plan with `--profile predator-3070`
and a new campaign id at the same pair, scaffold pending evidence and repeat
all gates using reviewed portable checks. Any automation fix reopens Nitro.
No receipt by itself authorizes a tag, release or compatibility promotion.

## Synthetic fixture rehearsal

**Synthetic examples only.** This complete command sequence uses made-up commits,
logs and all-true fixture observations. It exercises the real plan, scaffold,
probe, record, status and seal commands for both profiles; it observes no
hardware. Never copy its payloads into a real campaign. Run from this checkout
as an ordinary user. The independent test oracle supplies the fixture values,
so this is a software regression exercise, not a collector.

```bash
FIXTURE_DIR="${FIXTURE_DIR:-$(mktemp -d)}"
for PROFILE in nitro-3060 predator-3070; do
  mkdir "$FIXTURE_DIR/$PROFILE"
  python tools/release_acceptance.py --manifest release/acceptance.v3.yml plan \
    --profile "$PROFILE" --campaign-id "synthetic-$PROFILE" \
    --ansible-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    --bootstrap-sha bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
    --output "$FIXTURE_DIR/$PROFILE/plan.json"
  python tools/release_acceptance.py --manifest release/acceptance.v3.yml scaffold \
    --plan "$FIXTURE_DIR/$PROFILE/plan.json" --output "$FIXTURE_DIR/$PROFILE/evidence.json"
  python tools/release_acceptance.py --manifest release/acceptance.v3.yml status \
    --plan "$FIXTURE_DIR/$PROFILE/plan.json" --evidence "$FIXTURE_DIR/$PROFILE/evidence.json"
  if python tools/release_acceptance.py --manifest release/acceptance.v3.yml seal \
    --plan "$FIXTURE_DIR/$PROFILE/plan.json" --evidence "$FIXTURE_DIR/$PROFILE/evidence.json" \
    --output "$FIXTURE_DIR/$PROFILE/pending-receipt.json"; then
    exit 1
  else
    test "$?" -eq 2
  fi
  python - "$FIXTURE_DIR/$PROFILE" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, "tests")
from release_acceptance_contract import REVIEWED_V3_EVIDENCE, scalar_for

root = Path(sys.argv[1])
log = root / "synthetic.log"
log.write_text("Synthetic fixture only; no hardware observations.\n")
for gate_id, classes in REVIEWED_V3_EVIDENCE.items():
    probe = [sys.executable, "tools/release_probe.py", "--manifest",
             "release/acceptance.v3.yml", "payload", "--gate", gate_id]
    for field in classes["booleans"]:
        probe.extend(["--true", field])
    for field in classes["hashes"]:
        probe.extend(["--hash-file", f"{field}={log}"])
    for field in classes["descriptive"]:
        probe.extend(["--value", f"{field}={scalar_for(field)}"])
    payload = subprocess.run(probe, text=True, capture_output=True, check=True).stdout
    (root / f"{gate_id}.json").write_text(payload)
    recorded = subprocess.run(
        [sys.executable, "tools/release_acceptance.py", "--manifest", "release/acceptance.v3.yml",
         "record", "--plan", str(root / "plan.json"), "--evidence", str(root / "evidence.json"),
         "--gate", gate_id, "--status", "pass", "--summary", "Synthetic fixture only"],
        input=payload, text=True, capture_output=True, check=True,
    )
    report = json.loads(recorded.stdout)
    assert report["failed_gates"] == []
PY
  python tools/release_acceptance.py --manifest release/acceptance.v3.yml status \
    --plan "$FIXTURE_DIR/$PROFILE/plan.json" --evidence "$FIXTURE_DIR/$PROFILE/evidence.json"
  python tools/release_acceptance.py --manifest release/acceptance.v3.yml seal \
    --plan "$FIXTURE_DIR/$PROFILE/plan.json" --evidence "$FIXTURE_DIR/$PROFILE/evidence.json" \
    --output "$FIXTURE_DIR/$PROFILE/receipt.json"
  python tools/release_acceptance.py --manifest release/acceptance.v3.yml seal \
    --plan "$FIXTURE_DIR/$PROFILE/plan.json" --evidence "$FIXTURE_DIR/$PROFILE/evidence.json" \
    --output "$FIXTURE_DIR/$PROFILE/receipt-again.json"
  cmp "$FIXTURE_DIR/$PROFILE/receipt.json" "$FIXTURE_DIR/$PROFILE/receipt-again.json"
done
```

Expected: pending status 0/19 and refused pending seal, then synthetic 19/19,
ready true and byte-identical local fixture receipts with schema version 3.
Any nonzero command other than the deliberately refused pending seal, missing
gate, coerced boolean or differing receipt is a software failure.
