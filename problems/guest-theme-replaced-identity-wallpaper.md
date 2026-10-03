# A guest theme replaced the identity wallpaper

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest workspace shell
contract. The physical recheck on `dev-01` is pending.

## Symptom

On `dev-01`, `ALT+SHIFT+T` to `sakura-circuit` changed the colours and also
replaced the dev wallpaper with the sakura one.

## Root cause

The theme controller took the wallpaper from the pool of the theme being
applied, and changing theme also rotated the wallpaper. The wallpaper is the
part of the guest that shows which kind of Machine it is; a colour theme
should not take it away.

## Fix

The wallpaper always comes from the guest's identity theme, whatever theme
it wears; a guest without a recorded identity uses the theme's own pool.
Changing theme keeps the current wallpaper; only `ALT+SHIFT+W` rotates it,
within the identity pool.

## Regression proof

`tests/guest_workspace_shell_contract.py` applies the workstation theme and
then `sakura-circuit` to a dev guest and requires the theme to change while
both wallpapers stay in the `hyperlab-workstation` pool.
