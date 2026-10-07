# Independent architecture review: the reviewer's package

Roadmap milestone 0 asks for an independent review that actually reads the
repository. This page is what a reviewer needs to start; it is not the
review. The earlier attempt could not open the repository and does not
count; the C9 review of 2026-09-27
([`c9-independent-review-2026-09-27.md`](c9-independent-review-2026-09-27.md))
covered one milestone and is historical.

## 1. Reproduce the verification first

From the repository root, everything below must pass; it mirrors
`.github/workflows/ci.yml`:

```bash
ruff check .
ansible-lint
for pb in playbooks/*.yml; do ansible-playbook --syntax-check -i inventory.ini "$pb"; done
for t in tests/*_contract.py; do python3 "$t" || echo "FAIL $t"; done
for suite in tests/*-refusals.yml; do ansible-playbook -i inventory.ini "$suite"; done
python3 tests/schema_validate.py
python3 tests/schema_mutations.py
python3 tests/contract_mutations.py
python3 tools/hyperlabctl/tests/run.py
bats tests/*.bats
ansible-playbook -i inventory.ini tests/render.yml --extra-vars '{"hardware_profiles":{"nitro-3060":{"vfio_ids":["10de:2520","10de:228e"]}}}'
```

`tests/render.yml` has one task tagged `privileged` (`nft -c`) that needs
sudo; without it, add `--skip-tags privileged`. The QML contracts run
offscreen with `QT_QPA_PLATFORM=offscreen`; `HYPERLAB_RENDER_OUT=<dir>`
saves a capture per scenario. Software verification is not hardware
evidence: [`roadmap.md`](roadmap.md) keeps the two apart, and only a named
machine (Nitro) proves a hardware path.

## 2. Map of the repository

| Path | What it holds |
| --- | --- |
| `playbooks/` | the only entry points; host targets and one playbook per guest lifecycle operation |
| `roles/` | 31 roles: host (`base`, `kvm_host`, `vfio_boot`, `gpu_handoff`, `network_domains`, `lab_isolation`, `image_store`, `image_factory`, `workbench`, `host_desktop_*`), guest lifecycle (`guest`), guest profiles (`workstation_*`, `guest_*`, `dev_ide`), services (`service_*`, `jellyfin`) |
| `tools/` | typed planners and guards the roles call (`guest_plan.py`, `vfio_plan.py`, `image_plan.py`, `*_guard.py`), the Workbench, and `hyperlabctl/`, the operator CLI |
| `images/`, `templates/`, `vm-specs/`, `service-specs/` | checked-in policy: Golden Image manifests, Templates, fixture specs, service specs; `schemas/` defines them |
| `roles/host_desktop_common/files/quickshell/hyperlab/` | the host shell (QML) and its bridges `privatestack-machine-actions`, `privatestack-operation`, `privatestack-machine-provision` |
| `tests/` | contracts (`*_contract.py`), refusal suites, mutation tests, render invariants, bats |
| `docs/adr/` | architecture decisions; [`docs/adr/README.md`](adr/README.md) indexes them |
| `problems/` | every bug that changed a contract: symptom, root cause, fix, regression proof |

The product model is in [ADR 0021](adr/0021-product-lifecycle.md); start
there.

## 3. Trust boundaries to examine

- **Host decides, guest never claims.** Provenance, trust colour and GPU
  state come only from the host: the focused-surface resolver
  (`tools/surface_provenance.py`), the qemu hook (`roles/gpu_handoff/files/qemu`)
  and the domain metadata. Check that no guest-written value reaches them.
- **Privilege.** Every host change runs through `ansible-playbook -K`; the
  shell reaches it only through the operation runner, which resolves the
  command from the action registry and pins the checkout and spec digests.
  The checkout pointer `/etc/hyperlabctl/checkout` is root-owned trust.
- **GPU ladder.** Within one boot the GPU only moves clean → dev → dirty →
  lab ([ADR 0022](adr/0022-network-trust-and-gpu-policy.md)); the hook
  refuses an unmapped domain with PCI passthrough.
- **Images.** Sealed images are pinned by digest, receipts bind the manifest
  policy ([ADR 0010](adr/0010-image-provenance-transaction.md),
  [ADR 0024](adr/0024-rereceipt-after-policy-change.md)), captures and
  derivations are generalized and scanned ([ADR 0015](adr/0015-golden-image-capture.md),
  [ADR 0026](adr/0026-offline-derived-images.md)).
- **First contact with a Machine.** Its SSH host key is read through QEMU
  Guest Agent and pinned before any SSH connection; never accepted from the
  network.
- **Data crossing.** Host-to-guest clipboard is one host action to one named
  Machine over the pinned SSH channel ([ADR 0020](adr/0020-host-to-guest-clipboard.md));
  SPICE clipboard is off.

## 4. Decisions still proposed

| ADR | Question |
| --- | --- |
| [0019](adr/0019-gpu-lease.md) | a GPU-capable Machine choosing per run whether it owns the GPU |
| [0025](adr/0025-host-key-without-agent-file-reads.md) | pinning host keys without agent file reads |
| [0027](adr/0027-guest-notification-owner.md) | whether mako or the guest shell owns notifications |
| [0030](adr/0030-disposable-browser-image.md) | how the disposable browser image gets its session |
| [0031](adr/0031-service-appliance-templates.md) | how a service appliance is created from a Template |
| [0032](adr/0032-guest-clipboard-out.md) | clipboard out of a guest, to the host and to another guest |
| [0033](adr/0033-file-transfer-drop-folder.md) | files into a guest |
| [0034](adr/0034-usb-passthrough.md) | USB passthrough per Machine |
| [0035](adr/0035-microphone-and-camera.md) | microphone and camera per Machine and session |
| [0036](adr/0036-machine-snapshots-and-backups.md) | snapshots and encrypted backups of Machines |
| [0041](adr/0041-seamless-guest-applications.md) | seamless guest applications |
| [0042](adr/0042-network-device-machine.md) | the Wi-Fi card in a network Machine |
| [0043](adr/0043-usb-controller-machine.md) | the USB controller in a USB Machine |
| [0044](adr/0044-measured-boot.md) | a signed and measured boot with TPM2 unlock |
| [0045](adr/0045-looking-glass-stream-health.md) | Looking Glass stream health and a capture restart |
| [0046](adr/0046-nested-lab-host.md) | a nested lab host for host-level tests |
| [0047](adr/0047-emergency-stop.md) | one host key that pauses every Machine and cuts its network |
| [0048](adr/0048-key-vault.md) | a key vault: SSH keys in a Machine without a network |
| [0050](adr/0050-hardware-readiness-and-profile.md) | hardware readiness and a host profile proposal before install |
| [0051](adr/0051-disposable-viewer-and-safe-documents.md) | a disposable viewer and PDFs rebuilt from pixels |
| [0052](adr/0052-host-without-gpu-passthrough.md) | a host profile without GPU passthrough, chosen by name |

## 5. Questions the maintainer wants answered

1. QEMU Guest Agent filters by call, not by mode: allowing `guest-file-open`
   for the host-key read also allows opening a file for writing. Is the
   current exposure acceptable until ADR 0025 is decided?
2. Every Machine account keeps passwordless sudo until the end of its first
   provisioning (roadmap milestone 10). What is the right point and mechanism
   to remove it?
3. The operation runner trusts the checkout named by a root-owned pointer.
   Is pinning the checkout identity and the spec digest per operation
   enough, or should the runner verify a signed commit?
4. A disposable Machine's writes live in a libvirt transient overlay
   ([ADR 0018](adr/0018-disposable-discards-on-stop.md)). What happens to
   the overlay after a host crash, and can it leak a previous run's data?
5. The offline derivation lets apt reach the network from inside the
   libguestfs appliance. Is archive-key verification inside the base enough,
   or should packages be fetched and pinned by the host?
6. Which claims in the documentation overstate what the code enforces?

## 6. What the review should return

For each finding: severity, evidence (file and line, or a reproduction),
why it matters, the smallest fix, and the test that would have caught it.
Software findings and hardware findings separately. Nothing in the review
may describe HyperLab as providing Qubes OS security properties.
