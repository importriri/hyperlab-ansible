# Looking Glass Linux sender flags SDR frames as HDR PQ

Status: corrected, rebuilt/deployed and physically accepted on Nitro. The tested Linux SDR path now arrives as `hdr:0 pq:0`, and the Valley/Heaven colour presentation was physically accepted.

## Symptom

Guest colours shown by the host Looking Glass client for `arch-dev-vfio` are
wrong, although the host panel (`eDP-1`, `XRGB8888`, Hyprland colour preset
`srgb`) is SDR. The earlier mitigation, `egl:mapHDRtoSDR=no` for the
`linux-experimental` transport, was present on the running client.

## Root cause

The pinned PipeWire backend (`0140a3f6fb`) computes

```c
this->hdr   = info.format & (SPA_VIDEO_FORMAT_xBGR_210LE | SPA_VIDEO_FORMAT_RGBA_F16);
this->hdrPQ = true;
```

SPA video formats are sequential enum values, not flags. With libspa's values
(`RGBx=7`, `BGRx=8`, `RGBA=11`, `BGRA=12`, `RGBA_F16=78`, `xBGR_210LE=81`) the
mask is `95`, and every negotiated 8-bit SDR format tests non-zero. Every frame
therefore carries `FRAME_FLAG_HDR | FRAME_FLAG_HDR_PQ`.

The client acts on that in two independent places:

1. the EGL shader tone map (`isHDR && mapHDRtoSDR`) - disabled by the earlier
   `egl:mapHDRtoSDR=no` mitigation;
2. `setHDRImageDescription`, which on a compositor exposing
   `wp_color_manager_v1` (Hyprland 0.56) tags the surface as BT.2020 primaries
   with the ST2084 PQ transfer function. The compositor then converts sRGB
   pixels as if they were PQ. The earlier mitigation does not reach this path,
   which is why the problem returned once colour management was available.

## Fix

`pipewire-thread-loop-runtime.patch` additionally compares the format for
equality, so only `xBGR_210LE` and `RGBA_F16` are HDR, and PQ is asserted only
for HDR frames. The patch SHA is part of the sender rebuild stamp, so the next
`guest-looking-glass-linux.yml` run rebuilds the sender. `egl:mapHDRtoSDR=no`
stays: it remains correct for genuine HDR frames on an SDR path.

## Runtime acceptance — PASS

The rebuilt managed Linux sender was exercised on Nitro after the source
correction. The host Looking Glass client received the tested SDR stream with
`hdr:0 pq:0`, and physical Valley/Heaven colour presentation was accepted.

The managed `egl:mapHDRtoSDR=no` argument remains unchanged. No global
compositor colour-management disablement, VSync override or additional HDR
workaround was introduced.

`tools/looking_glass_colour_probe.sh` remains a read-only diagnostic. It
requires an actual received frame before it can report PASS, so an absent PQ
request without a frame is never treated as evidence.

This acceptance covers the tested SDR path. It does not make a broader claim
about genuine HDR/FP16 transfer semantics.

Classification:

`LOOKING_GLASS_SDR_VISUAL_ACCEPTANCE=PASS`
