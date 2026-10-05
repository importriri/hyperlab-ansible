# Allowed network flows

The frozen flow matrix between HyperLab's five network domains, the host
and the internet. `roles/lab_isolation` enforces it in the `inet
lab_isolation` table, `roles/network_domains` gives each domain its libvirt
network, and `tests/network_flow_matrix_contract.py` checks the rendered
ruleset against this page.

## Between guests and out

| From \ To | clean | dev | dirty | lab | services | internet |
|---|---|---|---|---|---|---|
| clean | same network | no | no | no | no | yes, NAT |
| dev | no | same network | no | no | no | yes, NAT |
| dirty | no | no | same network | no | no | yes, NAT |
| lab | no | no | no | same network | no | **no** |
| services | no | no | no | no | same network | yes, NAT |

Traffic between two domains is dropped in both directions, one rule per
ordered pair. `lab` has no libvirt forward at all and, at the host, nothing
enters or leaves its bridge through the forward hook: it is offline because
the host says so, whatever the guest is configured to do. A reviewed service
exposure forwards one LAN port to one service Machine
([`service-vm-contract.md`](service-vm-contract.md)).

## Guests to the host

Default deny. From each guest bridge the host accepts only:

- DHCP (UDP 68 → 67) on that bridge;
- DNS (UDP and TCP 53) to that bridge's own gateway, so no network can query
  another network's resolver;
- replies to connections the host opened, such as SSH and provisioning.

Everything else a guest sends to the host is dropped, IPv4 and IPv6 alike:
host services listening on every address (LLMNR, mDNS and the like) are
not reachable from any guest. The host itself reaches guests as it decides
(SSH over the pinned channel, the guest agent over its virtio port).

## Not yet

- Per-network VPN egress with a kill switch is not built.
