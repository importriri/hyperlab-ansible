# ADR 0023 - Gaming uses the existing trust identities, not a PLAY identity

Status: accepted by the operator on 2026-10-04.

## Context

Gaming needs three very different Machines: one that holds store accounts
that own purchases (Steam, Epic, GOG), one that runs modded games and
third-party launchers, and one for untrusted or cracked software that must
never reach the internet. Roadmap milestone 0 asks whether that needs a
separate PLAY identity, a sixth network and trust class, or whether the
existing classes suffice.

## Decision

No PLAY identity. Gaming Templates map onto the existing classes by what
the Machine holds and runs, not by the activity:

| Template | Network | GPU class | Holds |
| --- | --- | --- | --- |
| `gaming-clean` | clean | clean | store accounts and their purchases, nothing else installed |
| `gaming-dirty` | dirty | dirty | modded games and third-party launchers, never a store account |
| `gaming-offline` | lab | lab | untrusted or cracked software, no internet |

- The trust classes already say what matters: whose credentials the
  Machine holds and how much its code is trusted. A PLAY class would sit
  between existing rungs with no policy of its own, and would need its own
  network, firewall rules, ladder level, colours and review, for no
  isolation property the three rows above lack.
- The GPU ladder keeps its meaning: a clean gaming session must come before
  a dirty or offline one in the same boot, which is the protection a store
  account needs from modded code.
- Identity themes (`gaming-clean`, `gaming-dirty`) are presentation; they
  never stand in for the network colour on the host frame.

## Consequences

- No new network, rung or provenance identity is added; the matrix in
  roadmap milestone 9 stays five networks.
- Store accounts live only in `gaming-clean`; a modded or offline game never
  shares a disk, a network or a Machine with an account that owns
  purchases.
- If a later requirement needs a policy none of the classes expresses, that
  is the moment for a new identity, recorded in its own ADR.
