# The guest isolation let any undeclared bridge reach the host

Author: [importriri](https://github.com/importriri).

Status: corrected in source; covered by
`tests/lab_isolation_fail_closed_contract.py`; on Nitro once
`playbooks/foundation.yml` is applied.

## Symptom

Designing a network for the nested lab host (ADR 0046) showed that a new
libvirt network would not be isolated: its guests would reach the host's
services and the other networks' resolvers.

## Cause

The `inet lab_isolation` table filters with `policy accept` in both chains
and adds rules only for the five declared bridges. A bridge outside that
list matched no rule, so from it:

- the input chain accepted everything. Read without privilege on
  2026-10-05, the host listens on every address for LLMNR (TCP and UDP
  5355), mDNS (UDP 5353) and an unprivileged UDP port, and each network's
  resolver listens on its gateway, all reachable from such a bridge;
- the forward chain routed it to any declared network, since the pair rules
  name only declared bridges.

Any `virbr*` bridge libvirt creates (its stock `default` network, or one
defined by hand) was therefore outside the isolation, and nothing failed.

## Fix

Both chains now end with a catch-all: the input chain drops anything from a
`virbr*` bridge that the declared rules did not accept, DHCP included, and
the forward chain drops any route from one `virbr*` bridge to another. The
declared networks keep exactly their reviewed flows, and traffic that does
not come from a guest bridge (the host's own Wi-Fi, loopback) is untouched.
A network must now be declared to be usable at all.

## Regression proof

`tests/lab_isolation_fail_closed_contract.py` renders the shipped template
and evaluates packets with first-match semantics: from an undeclared bridge,
LLMNR, mDNS, another network's resolver and DHCP are dropped and no route
reaches another bridge, while the declared networks keep DHCP and DNS on
their own gateway and their NAT route. Against the previous template the
first case fails: the LLMNR packet is accepted. The frozen matrix contract
checks the two catch-all rules end their chains.
