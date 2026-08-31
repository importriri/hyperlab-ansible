# Nitro `arch-dev-vfio` acceptance — 2026-08-31

This receipt records the Nitro hardware observations made against local commit
`d1b7b9fe175d45051d326854b9755a84f17ca15c`. That commit is a direct child of public baseline
`5bb64271ebd8d553d5bc72c65a12aaf4e5d34545`.

The receipt is intentionally narrower than a final compatibility claim. It
records the evidence that is closed and keeps the remaining runtime checks
explicit.

## Mechanical gates

- `ARCH_DEV_VFIO_HOST_GATE_OK`: passed on the running 16 GiB domain with the
  reviewed RTX 3060 display/audio pair.
- guest reconciliation: second pass `changed=0`, `unreachable=0`, `failed=0`.
- repository `verify.sh`: passed after the Hyprland autologin validation fix.
- `ARCH_DEV_VFIO_GUEST_GATE_OK`: passed with RTX 3060 display and audio
  functions, kvmfr `0.0.12`, Looking Glass `B7-263-g0140a3f6fb`,
  `HEADLESS-0`, and the deterministic XDPH 144 Hz capture target.

## Interactive Looking Glass evidence

The physical-host client displayed the real `1920x1080@144` KVMFR feed.
Keyboard and pointer input worked inside the guest and the managed guest audio
path produced audible playback. The HyperLab lock screen accepted the guest
password and returned to the existing desktop.

Closing only the Looking Glass client did not own the guest session lifecycle:
Hyprland, the exact sender and `HEADLESS-0` remained alive. Reopening PRIMARY
reused that session and sender directly, did not open `virt-viewer`, and
PipeWire returned to streaming.

A clean Hyprland Lua exit then proved the opposite lifecycle boundary:
Hyprland and the exact sender both disappeared while Ly remained active.
Launching PRIMARY from that state opened the owned `virt-viewer` console for
Ly. Password input there was stable. HyperLab closed the temporary console
without operator intervention, created a fresh Hyprland session and sender, and
replaced the PRIMARY process with the reviewed Looking Glass client. The new
sender returned to PipeWire streaming on `HEADLESS-0` at `1920x1080@144`.

The temporary tty2 process-list diagnostic emitted an unrelated shell
interpolation warning after the authoritative logout checks had already
reported Hyprland absent, sender absent and Ly active. No acceptance decision
depends on that diagnostic line.

## Evidence identities

The raw local logs remain outside the repository. Their exact identities at the
time of this receipt were:

| Local evidence | SHA-256 |
| --- | --- |
| `20260831T180538Z-autologin-regex-repair/full-verify.log` | `b92b6c82d65ceb48670084113cdf1545960e4c9b806c3e591200963545c83e6b` |
| `20260831T180538Z-autologin-regex-repair/apply-2.log` | `b777842045101001d5aa706c7933fa07a2d7f580d16f9df4cd1ab176ff788674` |
| `20260831T181957Z-guest-gate-v2/guest-gate.log` | `10750efe0bea41d1db391c94223fdad0709684c765e466a6f709fbca621e2fda` |
| `20260831T183552Z-lg-reconnect/sender-reconnect.log` | `a6f235c13cebf09c44a774d8f656c5fa577f0bfefe39cf3b3d1a69d15702841b` |
| `20260831T185118Z-lua-logout-primary-handoff-v3/logout-lifecycle.log` | `f7d1ef845dc5dcfffffe0d36cbaa40ec47cbdef3edf9f2ae1a278d45a189ec5e` |
| `20260831T185118Z-lua-logout-primary-handoff-v3/virt-viewer.log` | `4f3443f6a6774cd97ac3f3a9b11482a2e53a28c51e8db4519e1910468757da3c` |
| `20260831T185118Z-lua-logout-primary-handoff-v3/final-client-argv.log` | `6892851f3f47edd3a6454be96c14f002c28e4fb54c2ff2b5538770a703470832` |
| `20260831T185118Z-lua-logout-primary-handoff-v3/post-handoff.log` | `f01aef2420d3abb88109bbc260f4b3d325b66cab4e0cbb6c22daca19dcb16d10` |

The visual observations were operator-confirmed during the same run. Current
controller/browser screenshots are not publication assets because they contain
workflow UI; clean media is a separate remaining task.

## Remaining acceptance

- real guest reboot and Looking Glass reconnect;
- final post-reboot idempotent guest pass;
- standalone `hyperlabctl open console` recovery recheck;
- host volume-step verification through the 125 percent software ceiling with
  an explicit no-clipping listening check;
- clean publication screenshot/video capture.

Secure Boot completion remains a separate hardware/security acceptance track.
