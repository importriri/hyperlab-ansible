# ADR 0040 - The security plane: host and network evidence, no command plane

Status: accepted (2026-10-05, host A and network A), extended with
off-host, append-only log shipping below. The host's audit rules and file
integrity checker are built; the network part, the shipping and the
Security Plane view are not.

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

## What this detects, and what it does not

auditd, AIDE and Suricata are detection, not prevention. They record that
something happened; none of them stops it. Code that becomes root on the
host can stop auditd, rewrite AIDE's database and delete the logs, so
evidence kept only on the host proves nothing about a host compromise: it
shows what happened up to the moment the attacker cared to hide it, and
only if it left the host before then.

## Off-host, append-only logs

The evidence is copied off the host as it is written, to a store the host
can add to but not change or delete.

**A. `systemd-journal-upload` to `systemd-journal-remote` on another device
(recommended).** The host's journal, which receives auditd's records through
the `audisp-syslog` plugin, AIDE's timer output and Suricata's alerts, is
streamed over HTTPS with a client certificate to a small receiver that is
not a HyperLab Machine. The receiver's store is append-only for the host's
identity: the host has no shell or file access there, and the receiver
rotates and keeps logs by its own policy. A Machine on Nitro is not off the
host: whoever controls the host controls it.
**B. Remote syslog (rsyslog with TLS)** to the same kind of receiver. Same
property, a second log format to keep.
**C. Periodic export to the backup disk** of
[ADR 0036](0036-machine-snapshots-and-backups.md). Not append-only in time:
an attacker edits the logs before the next export. Kept only as a copy.

In addition, and whatever the destination, the host journal is sealed with
forward-secure sealing (`journalctl --setup-keys`). The verification key is
written down off the host; `journalctl --verify` with it then shows whether
the local journal was altered after the fact. Sealing detects tampering, it
does not prevent it, and a root attacker can still delete the journal.

The Security Plane reports the age of the last record the receiver
acknowledged; Diagnostics shows log shipping as stale, not as healthy, when
that age passes a threshold.

The receiving device is the operator's to choose (`<LOG-SINK>` in the test
plan) and is a prerequisite for calling any host evidence trustworthy.

## Decision

Host A, network A and off-host logs A with forward-secure sealing, with the
Security Plane as above. Before any of them is enabled, its overhead is
measured on Nitro with `dev-01` under load, and a crafted event per rule
proves the evidence reaches Diagnostics and the receiver.

## Implementation

**Finding (2026-10-06).** Arch's repositories carry `audit` (core) but
neither AIDE nor Suricata (nor Zeek): they are only in the AUR, which
HyperLab does not install on the host. So:

- *File integrity*: a small reviewable checker replaces AIDE
  (`roles/host_integrity`, `/usr/local/bin/hyperlab-integrity`). It records
  the SHA-256, owner, group and mode of every file and link target under
  HyperLab's trust points, compares every hour from a hardened oneshot unit,
  and fails the unit and writes each difference to the journal. The first
  baseline is recorded once; later changes are accepted by the operator
  after review, never by the role.
- *Audit*: `roles/host_audit` installs `audit`, watches writes and attribute
  changes to the trust points under `hyperlab-*` keys (only paths that
  exist, since a missing one stops auditd loading later rules), sends the
  records to the journal through the syslog plugin, and checks the loaded
  rules. `playbooks/host-security-plane.yml` applies both;
  `tests/host_security_plane_contract.py` runs the checker on a temporary
  tree.
- *Network* (not built): with no Suricata package for the host, the IDS
  moves into a Machine. The host mirrors each guest bridge with `tc mirred`
  into one tap given to a minimal Debian Machine running Suricata, with no
  route and no address on that tap, so stopping it never stops a packet and
  it cannot send on the mirror. Its alerts reach the host only as files the
  host reads over the pinned SSH channel. This keeps option A's property
  and the host small.
- *Forward-secure sealing* is the operator's step: `journalctl
  --setup-keys` prints the verification key once, to be written down off
  the host.

## Hardware test

On Nitro, once the receiver exists: a crafted audit event (a write under a
watched path) reaches the receiver within the threshold; stopping
`systemd-journal-upload` turns Diagnostics' log shipping state to stale;
the host cannot delete or rewrite a record already on the receiver with its
own credentials; `journalctl --verify` with the off-host key passes on an
untouched journal and fails on a copy altered on purpose.
