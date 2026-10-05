# HyperLab threat model

What HyperLab protects against, what it does not, and where each claim is
checked. HyperLab is a Qubes-inspired compartmentalization on KVM: one
workstation, the operator's laptop, running Machines under KVM with libvirt
and QEMU on Arch Linux. It is not Qubes OS and
does not provide Qubes OS security properties: there is no Xen, no separate
GUI domain, no separate driver domains yet (ADRs 0042 and 0043 propose them
for the network card and the USB controller), no qrexec policy, and the
host's Linux kernel, KVM, QEMU and the host session are all in the trusted
base.

`tests/threat_model_contract.py` keeps this page honest: every open problem
in `problems/` must appear in it, and it may not claim what it says it does
not provide.

## Who is trusted

- **The host and its session** are the control plane. Whoever controls the
  host session controls every Machine; nothing on this page survives a
  compromised host.
- **The operator** decides every crossing: a Machine's creation, privilege
  through the operation window, each clipboard send, each GPU handoff.
- **Guests are not trusted**, the `dirty` and `lab` ones least. A guest's
  own claims, about its name, network, trust or state, are never used.

## What HyperLab protects against

| Threat | How | Where it is checked |
|---|---|---|
| A guest reaching another network's guests | every ordered pair of domains is dropped at the host; `lab` forwards nothing | [`network-flows.md`](network-flows.md), `tests/network_flow_matrix_contract.py` |
| A guest reaching the host's own services or another network's resolver | guest-to-host default deny: only replies, DHCP and DNS to its own gateway | same |
| A guest pretending to be a more trusted Machine on screen | provenance and trust colours come from the host's resolver and the Machine registry, never from the guest | [`hyperlab-shell.md`](hyperlab-shell.md), focused-surface provenance |
| A dirtier workload running on the GPU before a cleaner one in the same boot | the qemu hook enforces the ladder clean → dev → dirty → lab; services use a reviewed class | [ADR 0022](adr/0022-network-trust-and-gpu-policy.md), `tests/hook.bats` |
| A changed or unsealed image becoming a Machine | sealed images are pinned by digest and receipt and verified at every use | `tests/sealed_base_use_contract.py` |
| Trusting an SSH host key shown on the network | the first key is read through the QEMU Guest Agent and pinned | `tools/guest_host_key.py` |
| A guest running commands through the guest agent | after provisioning the agent answers only the calls HyperLab uses; `guest-exec` is refused and proven refused | `tests/guest_access_close_contract.py` |
| Data leaving or entering a guest silently | no SPICE agent channel, no shared folders, no USB devices or redirection, no SPICE file transfer; host-to-guest clipboard is one explicit action to one Machine | `tests/media_input_contract.py`, [ADR 0020](adr/0020-host-to-guest-clipboard.md) |
| A guest's display and input reachable from the network | SPICE listens only on a UNIX socket or loopback; the domain XML guard refuses any display server elsewhere, and any second one | `tests/graphics_exposure_contract.py` |
| A guest listening to the room | guests have a playback-only sound card and the Looking Glass client denies the microphone | `tests/media_input_contract.py` |
| A product Machine captured into a Golden Image | the Workbench refuses a domain with a Machine projection | `tests/workbench_contract.py` |
| A Template offering what its class forbids | the review gate at catalogue load and in CI | [ADR 0029](adr/0029-template-review-gate.md) |
| Guest data on an unencrypted disk | the VM store must be a dm-crypt mapping; host swap must be zram or dm-crypt | `tests/bootstrap_storage_contract.py`, `tests/host_swap_contract.py` |

## What HyperLab does not protect against

- **An escape from QEMU.** Every QEMU process runs as the same user with
  no MAC confinement, so code that escapes one Machine's QEMU can open every
  other Machine's disk
  ([`../problems/qemu-processes-share-one-identity.md`](../problems/qemu-processes-share-one-identity.md),
  [ADR 0037](adr/0037-qemu-process-confinement.md), proposed). An escape
  into the host kernel or KVM defeats everything here.
- **Hardware side channels** between Machines sharing the CPU, caches and
  memory: HyperLab pins vCPUs for performance, not as a side-channel
  defence.
- **What a GPU keeps across a reset.** The ladder assumes a reset removes
  nothing and orders uses so that does not matter within a boot; it does
  not inspect the GPU's state or firmware.
- **Writes through the guest agent's file calls.** The agent filters by
  call, not by mode: `guest-file-open` can open a file for writing
  ([ADR 0025](adr/0025-host-key-without-agent-file-reads.md), proposed).
- **Keyboard and pointer capture.** Looking Glass input isolation from host
  shortcuts is not yet accepted on hardware
  ([`../problems/looking-glass-input-isolation.md`](../problems/looking-glass-input-isolation.md)).
- **A compromise inside a Machine.** HyperLab contains a Machine; it does
  not protect a Machine from its own software.
- **Upstream supply chain** beyond the pinned checksums of base images and
  the archive keys inside them.
- **A tampered boot before the disk opens.** Secure Boot verifies the boot
  loader and the kernel with HyperLab's own keys, but not the initramfs or
  the kernel command line, and nothing is measured: whoever can write the
  EFI system partition can capture the disk passphrase
  ([ADR 0044](adr/0044-measured-boot.md), proposed).
- **Host drivers parsing outside input.** The host drives the Wi-Fi card
  and the only USB controller itself, outside IOMMU translation
  (`iommu=pt`): a flaw in their drivers or firmware is a flaw in the host
  ([ADR 0042](adr/0042-network-device-machine.md),
  [ADR 0043](adr/0043-usb-controller-machine.md), proposed). USBGuard
  ([ADR 0038](adr/0038-host-usb-device-policy.md), built, not yet applied
  on Nitro) keeps a new USB device's drivers away, but the host kernel
  still enumerates it.
- **Other physical access and firmware attacks.**
- **Host-side intrusion detection.** There is no HIDS or NIDS yet
  ([ADR 0040](adr/0040-security-plane.md), accepted, not built). Once built,
  auditd, AIDE and Suricata detect; they do not prevent. A root compromise
  of the host can stop them and erase what they wrote, so their evidence
  counts only once it has reached the append-only receiver off the host.

## Open problems

Every note in `problems/` still open, security-relevant or not, is listed
here so a reviewer sees them in one place:

- [`qemu-processes-share-one-identity.md`](../problems/qemu-processes-share-one-identity.md) — above.
- [`looking-glass-input-isolation.md`](../problems/looking-glass-input-isolation.md) — above.
- [`runtime-inventory-self-heal.md`](../problems/runtime-inventory-self-heal.md) —
  an on-demand action can find its ephemeral SSH inventory gone; an unsafe
  inventory is refused, and regenerating a missing one only through the
  authoritative inventory step is still an open gate.
- [`looking-glass-render-jinja-assertion.md`](../problems/looking-glass-render-jinja-assertion.md) —
  a verifier defect in a render gate.
- [`nitro-sense-dkms-provenance.md`](../problems/nitro-sense-dkms-provenance.md) —
  an open investigation into a hardware-driver install record.
