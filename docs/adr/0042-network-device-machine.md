# ADR 0042 - A network Machine owns the Wi-Fi card (sys-net)

Status: proposed. Nothing is built; the hardware test below decides it.

## Context

Roadmap milestone 10. The host drives the Wi-Fi card itself: `iwlwifi` and
the card's firmware parse every frame from any network in radio range, and
`iwd` and `systemd-networkd` on the host join those networks. A flaw in
that driver or firmware lands in the host, the control plane for every
Machine. The host also boots with `iommu=pt`, so a device the host drives
is not behind IOMMU translation: a compromised Wi-Fi firmware can reach host
memory by DMA. A device given to a Machine through VFIO is translated, and
reaches only that Machine's memory.

Read on Nitro without privilege on 2026-10-05:

| Device | PCI | IOMMU group | Reset | Host driver |
|---|---|---|---|---|
| Intel CNVi Wi-Fi `8086:06f0` | `00:14.3` | 7, alone | FLR | `iwlwifi` |
| Killer E2600 Ethernet `10ec:2600` | `07:00.0` | 15, alone | bus | `r8169` |

Interrupt remapping is present on both DMAR units. The card's Bluetooth
half is a USB device (`8087:0026`) on the USB controller, not part of this
function; it belongs to [ADR 0043](0043-usb-controller-machine.md).

A CNVi card has its MAC in the chipset and its radio on a companion module.
Running it in a guest is reported to work on other laptops, but it is
unproven on Nitro: this ADR stands or falls on the hardware test.

## Options

**A. A sys-net Machine owns the Wi-Fi card, the host routes through it
(recommended).** A minimal Machine, not offered in the Create view, gets
`00:14.3` as a managed VFIO hostdev and one virtio NIC on a new isolated
`uplink` network that only the host and sys-net share. Inside it, `iwd`
holds the Wi-Fi credentials and nftables masquerades the uplink to the
Wi-Fi interface; it listens on nothing from the uplink but the host's
pinned SSH channel. On the host the default route points to sys-net over
the uplink. The five network domains are unchanged: their libvirt NAT and
the `inet lab_isolation` rules stay on the host, which stays the only place
that decides which network reaches which. Only the egress interface changes
from `wlan0` to the uplink. Guests' DNS still goes to their own bridge
gateway; the host resolver forwards to sys-net. sys-net sees every flow as
coming from the host's uplink address, never which Machine sent it, and
nothing it says about a Machine is used.

The Ethernet card stays on the host as the recovery uplink until the Wi-Fi
path has been proven for a while; it then moves to sys-net the same way.

**B. Keep the card on the host.** No new Machine, no change to how the host
reaches the network; the exposure above stays.

**C. Give each network domain its own sys-net.** Separate egress per
domain, but one Wi-Fi card can only belong to one Machine. Rejected for
this hardware; per-network VPN egress (milestone 9) is the way to separate
egress later, inside sys-net.

## Giving the card back to the host

The hostdev is `managed='yes'`: libvirt detaches the card from `iwlwifi`
when sys-net starts and reattaches it when sys-net stops. The fallback is
therefore:

1. `virsh destroy sys-net` (or sys-net failing to start);
2. check the card is back on `iwlwifi`, otherwise
   `virsh nodedev-reattach pci_0000_00_14_3`;
3. `systemctl start iwd` on the host and restore the host default route.

The host keeps its own `iwd` configuration, disabled while sys-net runs, so
the fallback needs no typing of a Wi-Fi password. No boot entry binds the
card to `vfio-pci`, so no boot change is needed to fall back. The cost is
that the host drives the card from boot until sys-net starts; with `iwd`
disabled it joins nothing in that window.

## Consequences

- The host has no network until sys-net is up; sys-net is autostarted first.
- Captive portals are answered from a disposable browser Machine, whose
  traffic reaches sys-net like any other.
- Host updates go through sys-net too.

## Hardware test

On Nitro, with the commands in the operator's test plan:

1. Before: the card's driver, `ip route`, `resolvectl status`, the host
   `iwd` state, and `virsh net-list --all`.
2. sys-net created and started: the card is on `vfio-pci`; inside sys-net
   the card is seen, joins the network and reaches the internet; the
   guest's kernel log shows no firmware error.
3. Host default route through the uplink; `dev-01` reaches the internet;
   `lab` stays offline; the live `inet lab_isolation` ruleset matches the
   frozen flow matrix; a guest still cannot query another network's
   resolver.
4. sys-net stopped and started three times: the card works each time (FLR
   is enough to reset it).
5. Suspend and resume with sys-net running: Wi-Fi comes back.
6. The fallback above, timed: the host is back on Wi-Fi without a reboot.
