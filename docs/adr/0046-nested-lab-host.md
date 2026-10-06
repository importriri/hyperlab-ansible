# ADR 0046 - A nested lab host for host-level tests

Status: proposed.

## Context

Most of the test plan needs root on the host: playbooks with `become`, the
guest-to-host firewall, USBGuard, the AppArmor boot entry, close-access on a
throwaway Machine, the measured boot of ADR 0044. On Nitro each of those is
the operator's to run, one at a time, which makes the plan slow, and a
mistake lands on the only workstation. Read without privilege on
2026-10-05:

- nested KVM is on (`/sys/module/kvm_intel/parameters/nested` is `Y`);
- the host has 31 GiB of RAM, about 7.6 GiB free while `dev-01` (16 GiB),
  `arch-dev` (6 GiB) and `srv-tz-01` (2 GiB) run, and 4 cores with 8
  threads;
- the encrypted store has 381 GiB free;
- `edk2-ovmf` (Secure Boot firmware, empty variables) and `swtpm` 0.10 are
  installed;
- the host's guest isolation dropped only what came from the five declared
  bridges; any other bridge reached the host's services
  ([`../../problems/guest-isolation-skipped-unknown-bridges.md`](../../problems/guest-isolation-skipped-unknown-bridges.md),
  corrected first).

## Options

**A. One lab host VM, installed like the host, managed by a script without
privilege (recommended).** `tools/lab/hl_lab.py` creates, as the operator's
user against `qemu:///system`, only resources named `hl-lab-*`:

- the network `hl-lab-testbed` (bridge `virbr-hl-lab`, 10.10.9.0/24, NAT for
  packages), declared in `group_vars/all/networks.yml` and in the flow
  matrix: it reaches the internet and nothing else, and the host accepts
  from it only replies, DHCP and DNS on its own gateway;
- the storage pool `hl-lab-pool` under `/var/lib/libvirt/images/hl-lab` (the
  encrypted store) and its volumes: the 80 GiB disk, the Arch ISO (checked
  against the release signature before use), and a cloud-init seed that puts
  the lab's own SSH public key into the live ISO;
- the domain `hl-lab-host`: 4 vCPUs with `host-passthrough` (nested VMX),
  4 GiB of RAM (what the host can spare with its Machines running), Secure
  Boot firmware in setup mode so `sbctl` can enroll its own keys, an
  emulated TPM 2.0, and no real device: no hostdev, no USB redirection, no
  shared folder or memory, no SPICE agent channel, the display on loopback.
  `tools/lab/hl_lab_check.py` refuses any other definition before it is
  defined and checks it again as libvirt holds it.

The script refuses any name without the prefix before it calls `virsh`, and
never calls `sudo`. Inside, `arch-bootstrap` installs the lab host as on
Nitro (LUKS2, Btrfs, systemd-boot), and this repository's host playbooks
make it a HyperLab host. There the agent working on HyperLab has root and
may run anything: playbooks with `become`, the firewall, USBGuard, boot
entries, nested Machines, close-access, deliberate breakage, the HyperLab
ISO. The SSH key pair is made for the lab and lives under
`~/.local/share/hyperlab-lab`; it is never the operator's.

**B. Test inside the product Machines.** No new VM, but a Machine is not a
host: no boot entries, no host firewall, no libvirt.

**C. A second physical machine.** The most faithful, and not available.

## Starting it

The lab network is isolated only by the host's `lab_isolation` table, which
`playbooks/foundation.yml` loads with privilege. The script cannot read the
loaded ruleset, so it never claims the isolation: `start` refuses until the
operator has listed the loaded input chain, seen the `virbr-hl-lab` rules and
the `virbr*` catch-all, and says so with `--isolation-checked`. Defining the
resources starts nothing.

## Recommendation

A.

## What this does not cover

Anything that needs the real hardware stays on Nitro: the RTX 3060 and
VFIO, Looking Glass, the internal keyboard and touchpad, the physical Wi-Fi
and USB controllers, the Nitro's own firmware, Secure Boot keys and TPM. A
pass in the lab is "lab-verified": the software does what it should on a
host like Nitro's; it is not a Nitro result, and the test plan marks each
item as one or the other.

## Hardware test

On Nitro, once the isolation is loaded:

1. `sudo nft list chain inet lab_isolation input` shows the `virbr-hl-lab`
   rules and the `virbr*` catch-all; `hl_lab.py start --isolation-checked`
   starts the network and the lab host.
2. `virsh dumpxml hl-lab-host` shows no hostdev, no redirdev, no filesystem,
   an emulated TPM and Secure Boot firmware.
3. From the lab host, `ping 10.10.3.1` and connections to the other guest
   subnets fail, LLMNR and other host ports are unreachable, DNS through
   `10.10.9.1` and the internet work.
4. `arch-bootstrap` installs; the lab host boots with LUKS2 and
   systemd-boot; `sbctl status` shows setup mode; `/dev/kvm` exists inside
   and a nested Machine starts.
