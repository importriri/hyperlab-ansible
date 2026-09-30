# Visible tearing or presentation artefacts in the Linux guest benchmark path

Author: [importriri](https://github.com/importriri).

Status: physically localized and non-blocking for HyperLab. The Valley-specific flicker is already present in direct guest/X11 capture before the Looking Glass presentation path. Heaven is clean on the same guest pipeline. The exact Valley/OpenGL/GLX/Xwayland root cause remains intentionally unclaimed.
No deployment or performance tuning was performed in this investigation.

## Physical symptom and reproduction

The user sees tearing/presentation artefacts in Unigine Valley/Heaven on Nitro's
`arch-dev-vfio` through Looking Glass. SDR colours are now visually correct after
the reviewed PipeWire patch rebuild. The user remembers a previous solution;
there is not yet evidence establishing that this is the same failure mechanism.
Record whether the artefact is a horizontal discontinuity inside a frame,
repeated/dropped frames, uneven motion, or another corruption; do not conflate
these observations under a benchmark FPS result.

Affected path: application/Xwayland or Wayland -> guest Hyprland `HEADLESS-0`
1920x1080@144 -> portal/PipeWire -> Linux sender -> kvmfr -> host Looking Glass
renderer -> host Hyprland -> physical display.

## Historical evidence

- `21f47aa` introduced guest `general.allow_tearing=false`.
- `0a39da5` introduced the same explicit policy in the host Lua skeleton.
  Both remain false today, including through the guest template migration
  `a822713` and namespace change `24e2b43`.
- `git log --all -S'tearing' -- roles` finds those two introductions, not a
  later removal. Searches for `vsync`, `direct_scanout`, and `explicit_sync`
  in role history find no removed managed setting. Window/layer rule history
  does not reveal a guest immediate-mode exception that was lost.
- `bc28941` repaired PipeWire buffer ownership/locking after a **crash** under
  fullscreen rendering; `f024b77` repaired disconnect lifetime. These are
  relevant capture invariants, not documented proof of a tearing repair.
- The current colour patch additionally corrects SDR frames being flagged HDR/PQ.
  It is a separate fix and is preserved byte-for-byte in this work.

The exact recovered compositor policy is **disallow tearing on both sides**.
No source drift explains the current physical symptom. A historical local
runtime override, if one existed, still needs its own evidence.

## Proven root cause

Not established for the reported physical artefact. Compositor no-tearing policy
alone cannot establish whether a captured frame is internally consistent or
whether the two output clocks and client presentation are paced appropriately.
The installed pinned client source defaults `egl:vsync` to false and uses it for
`eglSwapInterval`, but repository history does not show a change to that default
or a removed override. That observation is a diagnostic lead, not a proven cause
and not justification to silently enable or disable it.

The gaming telemetry role records frame timing and does not configure compositor
tearing or a benchmark FPS cap. Its result cannot substitute for presentation
acceptance. A headless capture rate is also not evidence of physical scanout VRR.

## Implemented change and rejected alternatives

No speculative tearing setting is changed. The new rendered guest contract
requires explicit `allow_tearing=false`, checks the same host policy, rejects
immediate tearing rules, and preserves HEADLESS-0, 144 Hz capture, the colour
patch and buffer-lifetime guards. This closes a test coverage gap, not the
physical symptom at that stage.

Reject global `allow_tearing=true`, broad `immediate` rules, disabling compositor
colour management, reverting the SDR fix, killing Waybar, or declaring an FPS
limit to be a presentation fix. Do not add unmeasured VRR, direct-scanout, explicit
sync, or EGL swap-interval overrides merely because their names sound relevant.

## Deterministic regression coverage

`python tests/guest_presentation_contract.py` exercises rendered policy and
rejects enablement/removal of the guest no-tearing setting. It validates the host
no-tearing setting and checks sender patch content against the managed SHA256.
Adjacent Linux capture, headless picker, NVIDIA, gaming telemetry and input
contracts continue to apply. A static PASS never means the display is tear-free.

## Physical localization — 2026-09-29

The physical investigation localized the reported symptom substantially
further than the initial report.

Observed controls and A/B results:

1. Valley viewed through Looking Glass shows intermittent frame/HUD/text
   flicker.
2. Heaven on the same guest and presentation pipeline does not show the
   corresponding symptom.
3. A temporary client with `egl:vsync=yes` produced no visible improvement.
4. A separate single-variable client with `egl:noSwapDamage=yes` produced no
   visible improvement.
5. Neither temporary EGL experiment changed persistent configuration.
6. A roughly ten-second `wf-recorder` capture taken directly from guest
   `HEADLESS-0` contains the same Valley flicker when replayed independently
   on the host.
7. A separate `ffmpeg` `x11grab` capture of Valley's visible X11 window also
   contains the same flicker.
8. Removing Valley's `GPUMonitor` plugin while preserving `prime-run` and the
   remaining launch parameters leaves the symptom unchanged.
9. Changing only Valley's internal `video_fullscreen` value from `1` to `0`
   also leaves the symptom unchanged.

The direct X11 evidence means the observed Valley artefact is already present
before the downstream guest-output / PipeWire / kvmfr / Looking Glass client /
host-compositor presentation chain. The investigation therefore does not
support treating this symptom as a Looking Glass or HyperLab presentation
regression.

The remaining causal scope is application-specific around Valley and its
OpenGL/GLX/Xwayland rendering path. This record deliberately does **not**
claim which component inside that scope is defective: that narrower root cause
was not proven and is not required to accept the HyperLab C9 presentation
path.

The no-tearing source policy remains unchanged. No persistent VSync,
double-buffer, swap-damage, VRR, direct-scanout, explicit-sync or immediate
tearing override is introduced as a result of this investigation.

Heaven remains the negative control demonstrating that the same HyperLab guest
presentation path can render a comparable benchmark without this Valley
symptom.

Classification:

`C9_B=LOCALIZED_NONBLOCKING_APPLICATION_SPECIFIC`

`LOOKING_GLASS_REGRESSION_EVIDENCE=NO`

`HYPERLAB_PRESENTATION_BLOCKER=NO`
