# Nitro Secure Boot acceptance

Secure Boot is an explicit hardware acceptance gate for the Nitro AN515-55
pipeline. Signed files alone do not make the host Secure Boot complete.

## Acceptance states

The campaign uses these states:

1. **PREPARED** — HyperLab key material exists and the tracked boot artifacts
   verify as signed.
2. **ENROLLED** — the intended HyperLab hierarchy and required vendor trust have
   been enrolled into the firmware.
3. **ENABLED** — the running firmware reports Secure Boot enabled.
4. **MODULE TRUST REVIEWED** — out-of-tree modules have a documented trust
   behaviour for the selected lockdown/module-enforcement policy.
5. **HARDWARE PROVEN** — the host boots and the VFIO, Nitro and Looking Glass
   hardware paths pass their runtime gates.

No earlier state may be described as Secure Boot complete.

## Nitro enrollment policy

The reviewed first-enrollment candidate for this Acer is deliberately
conservative:

- HyperLab owns the active Platform Key;
- HyperLab KEK and db are enrolled;
- Microsoft certificates are retained for Option ROM compatibility;
- firmware-builtin Acer `db` and `KEK` certificates are retained;
- the previous Acer Platform Key is not retained as the active PK.

The pre-enrollment audit found an Option ROM in the boot chain. The enrollment
must therefore not bypass the `sbctl` Option ROM guard. In particular,
`--yes-this-might-brick-my-machine` is not an accepted HyperLab procedure.

The firmware exposes `dbDefault`, `KEKDefault` and `PKDefault`. Preview evidence
showed that adding firmware-builtin `db,KEK` enlarged the candidate db and KEK
lists while leaving the HyperLab PK list unchanged.

## Recovery boundary

Before firmware key changes, keep a root-only local recovery set containing:

- the currently enrolled firmware certificates;
- the HyperLab `sbctl` hierarchy;
- the DKMS signing key and certificate used by the current machine;
- the final enrollment preview;
- checksums and the pre-change `sbctl` status/verification output.

Private keys and recovery material are machine-local evidence. They must never
be committed, copied into public artifacts or included in release bundles.

## Lockdown is a separate gate

On the audited host, the active VFIO boot entry does not request lockdown, the
running lockdown state is `none`, and module signature enforcement is not
forced.

Secure Boot enrollment must therefore be completed and proved independently
from any future lockdown change. A later lockdown/module-enforcement campaign
must prove that required out-of-tree modules remain usable through an explicit
trusted signing path before it changes the VFIO default.

## Out-of-tree modules

`kvmfr` and `linuwu_sense` are signed by the machine's DKMS signing key. During
the pre-enrollment audit that certificate was not present in the kernel
secondary or machine trusted keyrings, and the running kernel was permissive
for module signature enforcement.

This is **OPEN**. A cryptographic signature is not treated as trusted-module
proof until the selected enforcement policy verifies it through an accepted
kernel trust path.

## Hardware proof after enrollment

The first successful Secure Boot boot is not sufficient by itself. The Nitro
gate must prove:

- the firmware reports Secure Boot enabled;
- `linux-hardened` boots through the signed loader/kernel path;
- the selected lockdown and module-enforcement states match policy;
- IOMMU and interrupt remapping remain active;
- both RTX 3060 functions bind to `vfio-pci` on the host;
- `kvmfr` loads and Looking Glass can use the managed path;
- `linuwu_sense` loads and the reviewed Nitro controls work;
- the accelerated Arch guest starts and sees a healthy NVIDIA device;
- a second boot does not change the result.

Only after these checks may the Nitro Secure Boot gate be marked GREEN.
