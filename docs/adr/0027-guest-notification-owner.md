# ADR 0027 - Who owns notifications in the guest workstation

Status: proposed. The operator chooses before the shell draws notifications;
today mako owns them, and a quiet Desk is built on mako's modes.

## Context

The roadmap asks for shell-owned notifications with a do-not-disturb mode per
Desk in the guest Workspace Shell. Two constraints already hold for that
shell ([`../guest-workspace-shell.md`](../guest-workspace-shell.md)):

- nothing depends on the shell being up: every key works without it, and a
  shell that keeps failing falls back to Waybar;
- the shell is restarted after a crash, so it can be absent for a few
  seconds at any time.

Only one process can own `org.freedesktop.Notifications` on the session bus.
mako owns it today; it is started at login and is also D-Bus activated, so a
notification sent before it runs starts it. Quickshell 0.3 offers a
`NotificationServer` that can take the name instead.

The per-Desk quiet state does not depend on the owner: `hyperlab-desk`
records which Desks are quiet, reports it in `status`, and sets the
daemon's mode when the Desk in front changes. That part is built.

## Options

**A. mako stays the owner; the shell drives and shows it.** mako keeps the
name and draws the notifications, styled by the theme. The shell reads the
quiet state from `hyperlab-desk status`, shows it in the status island, and
may list waiting notifications from `makoctl list -j`. A shell crash loses
nothing: mako keeps running.

**B. The shell owns notifications, mako as fallback.** The shell's
`NotificationServer` takes the name and draws notifications as islands. The
session supervisor starts mako when the shell is given up for Waybar.
Notifications sent while the shell is restarting either fail or D-Bus
activate mako, which then holds the name until it exits; the shell must
detect that and take the name back. Two drawing paths, and a handover to
test on every restart.

**C. The shell owns notifications, no fallback.** Simplest code. Breaks
"nothing depends on the shell": with the shell down, notifications are lost
or start a stray daemon.

## Recommendation

A. It gives the visible part the roadmap wants (a quiet Desk, an indicator,
a list of what waited) without a second notification path or a name
handover on every shell restart. B can follow if the shell needs to draw
notifications itself, with the handover proved by a contract first. C is
rejected.

## What is built either way

- `hyperlab-desk quiet on|off|toggle [--desk N]` and `quiet sync`; the state
  lives in the Desk state file, and `status` reports `quiet`;
- the mode follows the Desk in front through `makoctl mode -a|-r
  do-not-disturb`; Hyprland runs `quiet sync` at session start;
- mako's quiet mode hides everything except critical notifications and the
  helper's own confirmation. It is mako's own documented do-not-disturb form
  (`mako(5)`): hidden notifications are not dropped, and those still pending
  show again when the mode is removed;
- `ALT+SHIFT+N` toggles the Desk in front.
