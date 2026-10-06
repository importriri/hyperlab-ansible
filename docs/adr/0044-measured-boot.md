# ADR 0044 - Measured boot: signed unified kernel images and TPM2 unlock

Status: proposed. The UKI builder is built behind a switch that is off;
every step that changes how Nitro boots stays the operator's to run.

## Context

Roadmap milestone 10 asks for a boot chain whose every piece is verified
before the encrypted disk opens. What Nitro showed on 2026-10-05, read as
the operator's user without sudo, command by command:

- `bootctl status`: `Secure Boot: enabled (user)`, `TPM2 Support: yes`,
  `Measured UKI: no`, `Measured OS: no`;
- `sbctl status`: `Setup Mode: Disabled`, `Secure Boot: Enabled`, owner GUID
  set, `Vendor Keys: microsoft builtin-db builtin-KEK`
  ([`../nitro-secure-boot-acceptance.md`](../nitro-secure-boot-acceptance.md)
  explains why: the enrollment audit found an Option ROM in the boot chain);
- `/var/lib/sbctl/files.json`: the files `sbctl` signs are
  `EFI/BOOT/BOOTX64.EFI`, `EFI/systemd/systemd-bootx64.efi` and
  `vmlinuz-linux-hardened`, nothing else;
- `ls /boot /boot/loader/entries /boot/EFI/Linux` and
  `/boot/loader/loader.conf`: type 1 entries with a separate
  `initramfs-linux-hardened.img`, no unified image in `EFI/Linux`, and
  `editor no`;
- `lsblk -o NAME,TYPE,FSTYPE`: `nvme0n1p2` is `crypto_LUKS`, opened as
  `cryptroot`; `/etc/mkinitcpio.conf` has the `sd-encrypt` hook and
  `/proc/cmdline` has `rd.luks` options;
- `/sys/class/tpm/tpm0/tpm_version_major`: `2`;
- `df -h /boot`: a 1 GiB ESP with 859 MiB free; `ls -la /boot`: the
  initramfs alone is 132 MiB.

Not seen, because it needs root: the LUKS version and key slots
(`cryptsetup luksDump`), whether the TPM already holds anything, `sbctl
verify`, and the firmware's `db` itself. The operator's test plan reads
them first.

The gap: the initramfs and the kernel command line are neither signed nor
measured. Anyone who can write the ESP, offline or as root, can replace the
initramfs with one that records the LUKS passphrase, or point an entry at a
different `root=` or `init=`, and Secure Boot still passes. Secure Boot today
proves the loader and kernel, not the boot.

## Options

**A. Signed unified kernel images, then TPM2 with a PIN (recommended).**

1. *UKI.* Kernel, microcode, initramfs, command line and os-release become
   one PE file in `EFI/Linux/`, signed with the existing `sbctl` keys, so the
   firmware verifies all of it. The boot profiles of `roles/vfio_boot`
   (Hardened, Vfio, Vfio with AppArmor, Integrated, Nvidia) become profiles
   of one multi-profile UKI built with `ukify` (systemd 257 or later; the
   host has 261); systemd-boot lists each profile as an entry. One file per
   profile would need about 780 MiB of ESP, with no room left for the
   previous set during an update. The UKI is rebuilt and re-signed after every kernel or initramfs
   change, by the same hook that rebuilds the initramfs, and `sbctl verify`
   must pass before the hook succeeds.
2. *Measurement.* `systemd-stub` measures each UKI section into PCR 11. The
   build signs the expected PCR 11 values with a dedicated key
   (`ukify --pcr-private-key`), so a kernel update does not need a new TPM
   enrollment, and a boot of anything else (a type 1 entry, another UKI)
   does not match.
3. *TPM2 unlock.* `systemd-cryptenroll` adds a TPM2 slot bound to PCR 7
   (Secure Boot state and keys) and to the signed PCR 11 policy, with a PIN
   (`--tpm2-with-pin=yes`). The passphrase typed at boot today keeps its
   slot as the fallback. A TPM-only slot is not recommended on a laptop: a
   stolen Nitro would boot to the login screen with the disk open, leaving
   the volume key to memory and bus attacks.
4. *Recovery key.* `systemd-cryptenroll --recovery-key` adds a generated key,
   shown once, written down off the host (paper or the operator's password
   manager on another device), never stored on Nitro or in this repository.

**B. Signed UKI only, passphrase unlock as today.** Closes the initramfs
and command-line gap; no TPM. The passphrase is still typed into a verified
initramfs, which is the main gain.

**C. Sign the initramfs separately, keep type 1 entries.** systemd-boot does
not verify an initrd or an entry's command line, so this closes nothing.
Rejected.

## Microsoft keys

They stay enrolled. The enrollment audit found an Option ROM in the boot
chain, and on a laptop with an RTX 3060 behind the Intel display the
firmware may need a Microsoft-signed GPU Option ROM to show anything before
the kernel. Removing them is a separate step, only after the TPM event log
names every Option ROM measured at boot and each one is shown to be signed
by a key that stays. Removing them blind can leave Nitro with no display
before the kernel, which is a brick for an operator without the firmware's
own reset path.

## Brick risk and rollback

- *Nothing new is written to the firmware.* The keys are already enrolled;
  this ADR only changes files on the ESP and LUKS key slots. The firmware
  brick class (a wrong PK or `db`) is not touched.
- *An unsigned or broken UKI.* The firmware refuses it and systemd-boot
  shows the menu. The existing type 1 entries stay until the UKI has booted
  every profile and passed the checks below, and the previous UKI stays as a
  second entry, with systemd-boot's boot counting (`+3` tries) falling back to
  it automatically.
- *No entry boots.* Firmware setup (F2) can turn Secure Boot off for one
  boot; the passphrase still opens the disk. The operator must know the
  firmware setup password before starting.
- *TPM unlock fails* (a `dbx` or firmware update changes PCR 7, a lost PIN, a
  cleared TPM): the passphrase slot opens the disk; the TPM slot is re-enrolled
  after the reason is understood. A failed TPM unlock is never answered by
  widening the PCR policy.
- *Passphrase forgotten and TPM unusable:* the off-host recovery key.

The type 1 entries are removed only at the end. While they exist, an
attacker can still make one the default and capture the typed passphrase;
the TPM slot does not unlock for them, which is the measured part, but the
passphrase does.

## Hardware test

On Nitro, in this order, with the commands in the operator's test plan:

1. Before: `sbctl status`, `sbctl verify`, `bootctl status`, the LUKS
   header's key slot list (`cryptsetup luksDump`, slots only, no key
   material), and a copy of the LUKS header kept off the root volume.
2. Install `systemd-ukify`; build and sign the multi-profile UKI; `sbctl
   verify` lists it signed; `bootctl list` shows each profile.
3. Boot each profile once by one-shot entry: the VFIO profile must show both
   RTX 3060 functions on `vfio-pci`, `kvmfr` loaded, `dev-01` starting with
   Looking Glass; `bootctl status` reports `Measured UKI: yes`.
4. Enroll the recovery key, write it down, and prove it opens the volume
   (`cryptsetup open --test-passphrase`) before enrolling the TPM.
5. Enroll the TPM2+PIN slot; reboot: the PIN unlocks; a wrong PIN falls back
   to the passphrase; a type 1 entry booted once by one-shot asks for the
   passphrase, not the PIN.
6. A kernel update rebuilds and re-signs the UKI and the PIN still unlocks
   without re-enrollment.
7. Only then: make the UKI the default and remove the type 1 entries.

## Implementation so far

`roles/measured_boot` (`playbooks/measured-boot.yml`,
`measured_boot_enabled: false`, `tests/measured_boot_contract.py`) builds
step 1 and the measured part of step 2 of option A. One profile per type 1
entry, with exactly that entry's command line (the contract compares
them), joined by `ukify` into `EFI/Linux/hyperlab.efi` with signed PCR 11
policies for the enter-initrd phase. The PCR signing key is made once and
never replaced, since a new key needs a new TPM enrollment. The image is
signed with `sbctl` and checked with `sbverify` against the host's `db`
certificate before it replaces the image in use, which stays as
`hyperlab-previous.efi`. An mkinitcpio post hook rebuilds it after every
initramfs. The role never changes the default entry, the type 1 entries,
the LUKS key slots or the firmware's keys: the TPM2 enrollment, the
recovery key and the removal of the type 1 entries stay the operator's,
first in the lab host (OVMF in setup mode, swtpm), then on Nitro.

## Out of scope

Kernel lockdown and module signature enforcement stay the separate gate of
[`../nitro-secure-boot-acceptance.md`](../nitro-secure-boot-acceptance.md):
`kvmfr` and `linuwu_sense` must have an accepted trust path first.
