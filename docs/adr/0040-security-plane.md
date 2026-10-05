# ADR 0040 - The security plane: host and network evidence, no command plane

Status: proposed. The operator chooses the tools; nothing is built.

## Context

Roadmap milestone 12 asks for an endpoint HIDS with measured overhead and
no remote-command plane into the hypervisor, a passive NIDS that is never
an inline dependency of routing, and a HyperLab Security Plane that
correlates both and shows the result in Diagnostics. The platform rules
apply: the host decides and a guest never claims; evidence comes before a
claim; nothing new may accept commands or trust from the network or a
guest.

## Options for the host

**A. auditd with a reviewed rule set, plus AIDE for file integrity
(recommended).** Both run locally, have no agent that takes commands, and
write to files the Security Plane reads. auditd watches HyperLab's own
trust points (the checkout pointer, `/etc/gpu-handoff`, the libvirt and
qemu hook directories, sudoers, the nftables drop-ins, the image store's
receipts); AIDE checks their content on a timer.
**B. Wazuh agent.** Rich rules, but its manager can push active responses,
which is the remote-command plane the roadmap excludes.
**C. osquery.** Good inventory queries; a daemon with an extension socket
and scheduled queries to review.

## Options for the network

**A. Suricata in IDS mode on a mirror of the guest bridges (recommended).**
The host mirrors each guest bridge to a dummy interface with `tc mirred`;
Suricata reads only the mirror, so stopping it never stops a packet.
Per-network rule sets: `lab` should be silent, any outbound flow there is an
alert. **B. Zeek** on the same mirrors, for connection logs rather than
signatures. **C. Inline IPS.** Rejected: an inline dependency.

## The Security Plane

A read-only host service reads the auditd and AIDE results and the IDS
alerts, ties each to the host-owned identity of the Machine and network it
concerns (from the Machine registry and the bridge, never from what a guest
says), and publishes a summary that Diagnostics shows: what fired, where,
when, and how fresh the evidence is. It has no write path into a guest or
the host configuration.

## Recommendation

Host A and network A, with the Security Plane as above. Before either is
enabled, its overhead is measured on Nitro with `dev-01` under load, and a
crafted event per rule proves the evidence reaches Diagnostics.
