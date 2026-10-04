# ADR 0020 - Host-to-guest clipboard is one host action aimed at one Machine

## Context

Machines have no shared clipboard: SPICE clipboard and file transfer are off
and the Looking Glass client is started without clipboard synchronisation.
Typing a long command or a URL into a guest by hand is the only way in.
Roadmap milestone 6 asks for host-to-guest clipboard through a dedicated
host key, with the target Machine chosen each time, and keeps the platform
rule: data crosses between host and guests only through an explicit,
one-shot, host-mediated action aimed at one named target.

Three transports exist:

- the SPICE agent, which synchronises continuously in both directions and
  lets the guest read the host clipboard whenever it likes;
- QEMU Guest Agent file writes, which would widen the agent beyond the read
  of the SSH host key that HyperLab uses today, while milestone 10 narrows
  it;
- the SSH channel HyperLab already trusts: the strict runtime inventory, the
  host key pinned through the guest agent, the operator's key.

## Decision

- **Transport.** `hyperlabctl clipboard send MACHINE` reads the host
  clipboard once with `wl-paste`, as text only, refuses empty, binary, non
  UTF-8 or more than 1 MiB, and pipes it over the reviewed SSH argv of
  `hyperlabctl open ssh` to one fixed guest program,
  `hyperlab-clipboard-receive`. The text never appears in an argument
  vector, a log, an operation record or the shell.
- **Receiver.** The workstation profile installs the receiver. It reads at
  most the same limit from stdin, checks UTF-8, finds the account's own
  Wayland session and hands the text to `wl-copy`. A Machine without the
  receiver, such as a server, refuses with a clear reason.
- **One target, chosen each time.** `SUPER + SHIFT + V` opens the launcher
  in a *Send clipboard to* mode that lists only running Machines, each with
  its host-resolved provenance. There is no default and no last-used
  target; Return on a Machine sends once. Escape sends nothing.
- **Boundary.** The machine bridge gains the verb `clipboard MACHINE`. It
  applies the same checks as SSH (a managed spec, a running domain, a valid
  runtime inventory) before it runs the reviewed command, and the shell
  records the outcome and its byte count, never the text.
- **Direction.** Only host to guest. Guest to host and guest to guest are
  later items of the same milestone and need their own decision, including
  confirmation when data moves to a higher trust class.

## Consequences

- No continuous channel exists; a guest cannot read the host clipboard.
- Sending to a lower-trust Machine is a deliberate act with the target
  named on screen; the provenance colour beside each target makes a dirty
  or lab destination visible before Return.
- The Machine must be reachable over SSH. An offline `lab` Machine is
  reachable from the host on its own network, like any SSH connection.
- The key sheet of the host lists the key; a generated host cheatsheet
  (roadmap milestone 6) will take it from the same binding model.
