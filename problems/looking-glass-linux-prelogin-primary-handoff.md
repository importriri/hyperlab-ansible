# Linux Looking Glass pre-login fallback input

Status: mitigated by PRIMARY handoff design; final hardware handoff proof pending.

## Symptom

On the Nitro `arch-dev-vfio` Linux VFIO guest, the Looking Glass client could
display Ly through its built-in SPICE display fallback while the Linux sender
was absent. The fallback image was physically visible, but password input
through the Looking Glass SPICE input path produced repeated or phantom key
events. The client also displayed its "Host Application Not Running" modal,
which is technically correct for an absent sender but conflicts with a login
flow where sender absence is intentional.

The standalone `virt-viewer` SPICE console accepted Ly password input normally.
A test with `spice:input=no` removed the Looking Glass INPUTS channel but did
not make the built-in fallback suitable as the authenticated PRIMARY login
surface.

A separate logout test showed that the on-demand Linux
`looking-glass-host` process could survive after Hyprland exited.

## Root cause boundary

The hardware campaign proves that the SPICE display fallback itself works and
that the standalone SPICE input path works. It does not prove a safe root cause
for the anomalous Looking Glass built-in fallback input. The Linux sender path
is project-specific experimental integration, so HyperLab does not depend on
that fallback for authentication.

The stale sender was caused by launching the sender detached with `nohup`
without tying its lifetime to the reviewed Hyprland compositor.

## Fix

For Linux experimental VFIO guests, `hyperlabctl open looking-glass` owns a
PRIMARY handoff:

1. if Hyprland is already ready, prepare the sender and open Looking Glass;
2. otherwise open the already-proven `virt-viewer` console as a temporary
   child;
3. wait a bounded interval for the Hyprland user session;
4. close only that owned temporary console;
5. wait until the reviewed `HEADLESS-0` capture output is actually present at
   1920x1080@144, rather than treating the first Hyprland PID as display
   readiness;
6. prepare the sender and replace the PRIMARY launcher with Looking Glass.

The first hardware handoff attempt exposed the readiness race: Hyprland existed
and login had succeeded, but the temporary console closed before the reviewed
headless output was ready. A manual Looking Glass reopen a few seconds later
immediately received BGRA 1920x1080 KVMFR frames, proving the normal sender
path was healthy and narrowing the failure to post-login readiness ordering.

`hyperlabctl open console` remains an independent recovery action.

The sender is started under a detached wrapper that owns the exact sender PID,
monitors the exact Hyprland process and stops the sender when Hyprland exits.
No persistent user service and no broad process kill are introduced.

## Closure gate

The issue is closed only after hardware proof confirms:

- PRIMARY opens Ly through the temporary SPICE console;
- Ly password input is stable;
- login reaches Hyprland;
- the temporary console closes automatically;
- Looking Glass opens with the reviewed KVMFR feed at 1920x1080@144;
- logout removes both Hyprland and the exact Looking Glass sender;
- standalone `open console` still works as recovery;
- Secure Boot, VFIO and KVMFR remain healthy.

## Hardware verdict

Nitro hardware testing rejected the Looking Glass built-in SPICE fallback as
the authenticated PRIMARY login surface for the Linux experimental guest.

The fallback display itself is proven: Looking Glass connects the SPICE
DISPLAY and CURSOR channels and renders Ly at 1280x800 while the Linux sender
is absent. The same path also connects the SPICE INPUTS channel, but repeated
or accumulated password input was observed during the campaign, and the
client continued to present host-not-running messaging while sender absence
was intentional. The warning that the keyboard channel is insecure remains a
separate open security gate.

The accepted PRIMARY path is therefore:

1. HyperLab opens a temporary owned `virt-viewer` console for Ly.
2. The user authenticates through the proven standalone SPICE input path.
3. HyperLab waits for Hyprland, its Wayland environment and reviewed
   `HEADLESS-0` at 1920x1080@144.
4. HyperLab closes only the temporary console that it owns.
5. The Linux sender starts under the Hyprland-bound lifecycle wrapper.
6. HyperLab opens the pinned Looking Glass client on KVMFR.

Hardware proof on the Nitro confirmed the automatic transition without a
manual Looking Glass reopen. Closing the host Looking Glass client leaves the
guest Hyprland session and sender alive. Logging out of Hyprland removes the
sender and returns the guest to Ly.

`hyperlabctl open console` remains the explicit recovery surface. The use of
`virt-viewer` inside PRIMARY is an implementation detail of the authenticated
handoff, not a second user-facing connection choice.

The built-in Looking Glass SPICE fallback remains useful diagnostic evidence,
but it is not part of the release PRIMARY authentication contract.
