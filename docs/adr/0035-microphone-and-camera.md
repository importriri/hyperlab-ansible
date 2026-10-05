# ADR 0035 - Microphone and camera per Machine and per session

Status: proposed. Today no domain definition gives a guest an audio input or
a camera; the contract `tests/media_input_contract.py` keeps it that way
until this is decided.

## Context

A microphone or a camera in a guest records the room. Roadmap milestone 6
asks for both off by default, on only per Machine and per session, with a
host indicator while active.

## Options

**A. PipeWire capture stream on demand (recommended).** The guest gets a
virtual sound card whose capture side is connected on the host only while a
host action holds it open, for one Machine and one session; the host shell
shows a recording indicator on the rail and on the Machine's card for as
long as the stream is linked. A camera is passed the same way, as a
PipeWire video stream the host links on demand. Nothing is linked at start.

**B. USB passthrough of the device ([ADR 0034](0034-usb-passthrough.md)).**
Reuses one mechanism, but the guest then owns the device completely and the
host can only show that it is attached, not that it is recording.

**C. No capture in guests.** Simplest; calls and recordings then happen on
the host.

## Recommendation

A for the microphone; for the camera, C until a workstation needs one, then
A. The indicator is host-drawn, never a guest claim.
