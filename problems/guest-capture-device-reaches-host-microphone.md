# Every guest has a capture device the host microphone can feed

Author: [importriri](https://github.com/importriri).

Status: the Looking Glass client denies the microphone; the guest capture
device is removed from new domain definitions and migrated out of existing
ones in a following change. Found by review, not observed on hardware.

## Symptom

None observed. Reviewing roadmap milestone 6 ("microphone and camera off by
default"), the domain template turned out to give every Machine an ICH9
sound card with a **duplex** codec, playback and capture, routed to SPICE
audio.

## Diagnosis

- `roles/guest/templates/domain.xml.j2` declares
  `<sound model="ich9"><codec type="duplex"/>` with `<audio type="spice"/>`,
  for every lifecycle and device profile. The guest therefore sees a
  microphone input, and QEMU offers the SPICE record channel.
- The Looking Glass client is started without `audio:micDefault`, whose
  default is `prompt`: when the guest opens its input, the client asks the
  operator in its window. Not silent, but one click from the host
  microphone.
- `virt-viewer` (spice-gtk) records from the host's default source when the
  guest starts capture, as far as its documentation and source show, without
  a prompt. This was not tested on Nitro: it needs a guest that records while
  its console is open.

## Cause

The sound device was added for playback ("the managed ICH9 SPICE sound
device") and took the codec's default shape, duplex, without a decision
about capture.

## Fix

1. `hyperlabctl open looking-glass` starts the client with
   `audio:micDefault=deny`.
2. New domain definitions get an output-only codec; an existing duplex
   domain is accepted as legacy and migrated when it is shut off and
   reconfigured.

## Regression proof

- `tests/looking_glass_launcher_contract.py` and
  `tests/media_input_contract.py` refuse a Looking Glass launch without the
  deny, or with `allow` or `prompt`.
- The codec change carries its own contract assertion.
