# A dev Machine could wear the clean and dirty identities

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest workspace shell
contract. The physical recheck on `dev-01` is pending.

## Symptom

On `dev-01`, `ALT+SHIFT+T` cycled into the `hyperlab-gaming-clean` and
`hyperlab-gaming-dirty` themes, with their identity wallpapers, inside a dev
Machine.

## Root cause

A design mistake in the rice profiles: the role installed all three identity
wallpapers on every guest and the theme controller offered every theme, so
that one guest could preview the others. An identity theme names a kind of
Machine and its network; a dev Machine dressed as clean says something false
about itself, even though only the host frame establishes trust.

## Fix

- The role installs only the selected profile's identity wallpaper, removes
  the identity themes of the other profiles, and records the guest's identity
  theme, root-owned, in `/etc/privatestack/guest-identity-theme`.
- The theme controller offers that identity theme and the neutral themes,
  refuses to apply another identity, and drops a recorded choice another kind
  of Machine owns. Without a recorded identity it offers no identity theme.

## Regression proof

`tests/guest_workspace_shell_contract.py` loads the controller with a dev
identity and requires `ALT+SHIFT+T` to stay within the dev and neutral
themes, a stale clean choice to fall back to dev, the dirty identity to be
refused, and the role to remove foreign identities and record its own before
the first prepare.
