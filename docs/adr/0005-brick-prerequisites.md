# ADR 0005 - Brick prerequisites are declared, not documented

## Context

`playbooks/looking-glass.yml` carries a comment saying to run
`playbooks/host-desktop-sway.yml` first. Run in the wrong order it still reports
success: packages install, the module builds, the client lands. What is
missing only shows up later, when the client cannot open the node,
because `TAG+="uaccess"` grants access to an active seat session and
without the cockpit there is none.

A prerequisite enforced by a comment is not enforced.

## Decision

Each brick records that it landed:

```
/etc/privatestack/bricks/<brick>
```

The graph is declared in one place, `group_vars/all/bricks.yml`:

```yaml
brick_requires:
  looking_glass: [desktop]
  dev_ide: [desktop]
```

A small `brick_guard` role asserts the prerequisites of the brick it is
guarding and fails closed with the exact command to run first. Playbooks
that need it list it as their first role.

## Consequences

- Wrong order fails in one second with an actionable message, instead of
  succeeding and disappointing an hour later.
- The graph is data. Adding an edge is a line, and a static test can
  check that every brick named exists and that the graph is acyclic.
- `hyperlabctl host doctor` gets a real thing to read: which bricks are
  on this host.
- Cost: one stamp task per role. That is the price of the guarantee, and
  it is paid once.
