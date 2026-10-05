# ADR 0033 - Files into a guest through a host-mediated drop folder

Status: proposed. The operator chooses before it is built; today no file
crosses between host and guests (SPICE file transfer and shared folders are
off in every spec).

## Context

Roadmap milestone 6 asks for file transfer into a guest: one file set and
one target per action, mediated by the host. The transports are the same as
for the clipboard ([ADR 0020](0020-host-to-guest-clipboard.md)): the SPICE
agent, QEMU Guest Agent file calls (which milestone 10 narrows), and the SSH
channel HyperLab already trusts.

## Options

**A. A host action over SSH into a per-Machine inbox (recommended).** The
operator picks files on the host and one running Machine; the host copies
them with the reviewed SSH argv into `~/Inbox/<date>-<n>/` of the
Machine's account, through a fixed guest receiver that refuses symlinks,
devices, paths outside the inbox and a total above a set size. Nothing runs
the files. Each transfer is logged on the host with the target, the file
names, sizes and sha256s.

**B. A shared virtiofs folder per Machine, mounted read-only in the guest
for one transfer.** Faster for large files, but it adds a filesystem device
to the domain definition and a mount that must be removed reliably after
the transfer.

**C. Guest Agent `guest-file-write`.** Rejected: milestone 10 removes file
writes from the agent.

## Recommendation

A. It reuses the pinned SSH channel, adds no device to the domain, and a
transfer is one bounded copy. Guest → host files are a separate decision,
like the clipboard's other directions ([ADR 0032](0032-guest-clipboard-out.md)).
