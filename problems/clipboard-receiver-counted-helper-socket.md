# The clipboard receiver counted awww's socket as a second session

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the clipboard crossing contract.
The physical recheck on `dev-01` is pending.

## Symptom

The first host-to-guest send on Nitro was refused by the guest, twice:

```text
hyperlabctl clipboard send dev-01
hyperlabctl: dev-01 refused the clipboard: HyperLab clipboard refused: no single graphical session is running for this account
```

SSH worked and Hyprland was running on `dev-01`.

## Diagnosis

Read on `dev-01` without privilege:

- `loginctl` listed the systemd user manager (`1`), two SSH logins (`12`
  active, `5` closing, both `Type=tty`, `Remote=yes`) and one seated Wayland
  session (`c1`, `Type=wayland`, `Remote=no`, `Seat=seat0`, from
  `ly-autologin`);
- `/run/user/1000` held `wayland-1`, `wayland-1.lock` and
  `wayland-1-awww-daemon.sock`.

## Root cause

The receiver never looked at logind. It took every socket named `wayland-*`
in the runtime directory as a session and required exactly one. The
wallpaper daemon `awww` puts its own socket there with the same prefix, so
every workstation guest showed two "sessions" and every send was refused.
The SSH logins were not the cause. The contract's fixture created only
`wayland-N` sockets, so it never met a real runtime directory.

## Fix

Delivery now requires both, and refuses otherwise:

- logind reports exactly one session of this account that is local
  (`Remote=no`), seated, of class `user`, of type `wayland` and active or
  online; SSH logins and the user manager never count;
- the runtime directory holds exactly one compositor display socket, named
  `wayland-<number>`; helper sockets with the same prefix are not displays.

## Regression proof

`tests/clipboard_crossing_contract.py` replays `dev-01` as it was: the four
logind sessions with their properties and a runtime directory with
`wayland-1`, `wayland-1.lock` and `wayland-1-awww-daemon.sock`. The text must
be delivered. Two local graphical sessions, only SSH logins, a remote Wayland
session, no compositor socket, two compositor sockets or only a helper socket
must each be refused. Against the previous receiver the contract fails with
the exact message seen on Nitro.
