# The guest config refused the gradient border string

Author: [importriri](https://github.com/importriri).

Status: corrected in source and pinned by the guest workspace shell contract.
The physical recheck on `arch-dev-vfio` is pending.

## Symptom

After the first deploy of the bolder guest look, Hyprland showed a red banner
over the session:

```text
Your config has errors:
/home/sid/.config/hypr/theme.lua:1: error setting 'general.col.active_border':
invalid color "rgba(5b8cffff) rgba(8fb0ffff) rgba(5b8cffff) 45deg"
```

## Root cause

The theme controller wrote the active border as the classic Hyprland gradient
string: several colours and an angle separated by spaces. The guest runs
Hyprland 0.56 with a Lua configuration, where `col.active_border` takes one
colour value and refuses that string. The presentation contract executes the
generated compositor configuration against a stand-in `hl` table, which
accepts any string, so it could not catch a value the real compositor
rejects.

## Fix

The border is one `rgba()` colour in the theme's accent, and the glow keeps the
accent. The turning-border animation was removed with the gradient it would
have turned. A gradient comes back only with its reviewed Lua form, listed in
the roadmap.

## Regression proof

`tests/guest_workspace_shell_contract.py` refuses an angle or a list of
`rgba()` values in the generated `theme.lua` colours.
