# Every guest could reach the host's own services and every resolver

Author: [importriri](https://github.com/importriri).

Status: corrected in source; the ruleset is checked by
`tests/network_flow_matrix_contract.py` and `tests/render.yml`. Applying it
needs `playbooks/foundation.yml` on Nitro, which owns the isolation brick. Found by review; the
listening sockets were read on Nitro, no traffic was sent.

## Symptom

None reported. Reviewing roadmap milestone 9 ("host firewall default deny
for guest-to-host traffic"), the isolation table turned out to have a
forward chain only.

## Diagnosis

- `roles/lab_isolation/templates/lab-isolation.nft.j2` dropped traffic
  between guest bridges and everything through the lab bridge, all in the
  forward hook. Nothing filtered the input hook, whose default policy is
  accept.
- On Nitro, read without privilege with `ss -ltnu` on 2026-10-05, the host
  listened on every address for LLMNR (TCP and UDP 5355), mDNS (UDP 5353)
  and one high UDP port, besides the five libvirt dnsmasq instances, each
  on its own gateway address.
- Linux answers on any of its addresses through any interface, so a guest
  on `dirty` could reach those host services and query `10.10.3.1`, the
  resolver of `dev`, and likewise every other network's resolver.

## Cause

The isolation brick was written as a forward matrix between domains; the
host as a destination was never part of it.

## Fix

The same table gains an input chain at priority -10 with policy accept, so
it only adds restrictions: from each guest bridge it accepts replies to
connections the host opened, DHCP on that bridge and DNS to that bridge's
own gateway, then drops everything else, IPv4 and IPv6. ARP is not in the
inet family and is unaffected.

## Regression proof

`tests/network_flow_matrix_contract.py` renders the ruleset and requires
exactly that input chain for every domain, and refuses a DNS rule that does
not name the bridge's own gateway; `tests/render.yml` counts the drops,
the replies and the DNS rules, and runs `nft -c` on the result where sudo
is available.
