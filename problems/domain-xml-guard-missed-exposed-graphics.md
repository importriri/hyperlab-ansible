# The domain XML guard missed a display server exposed beyond loopback

Author: [importriri](https://github.com/importriri).

Status: corrected in source; covered by `tests/graphics_exposure_contract.py`.

## Symptom

`tools/guest_xml_contract.py` compares a Machine's live inactive domain XML
with the one HyperLab renders, and the guest brick refuses to go on when
they drift. Given the rendered XML of a standard Machine as expected, it
answered `domain XML contract: OK` for an actual domain that also had

```xml
<graphics type="vnc" port="5900" autoport="no" listen="0.0.0.0">
  <listen type="address" address="0.0.0.0"/>
</graphics>
```

A domain edited by hand, or by anything else with libvirt access, could put
a guest's display, keyboard and pointer on every address of the host and
still be taken for a managed Machine.

## Cause

The signature the guard compares read one graphics device: the first
`<graphics>` for the listen address and the first SPICE one for its other
fields. A second device was not part of the signature at all. The listen
address was read from the `listen` attribute or a `<listen type="address">`
child only, so a `<listen type="network">` was reported as no address, and
nothing said that a missing address or a non-loopback one was wrong in
itself: only a difference from the expected XML was.

## Fix

`graphics_exposure` checks every graphics device of both files, apart from
the comparison: only SPICE and VNC are allowed, and each must listen on a
UNIX socket or on a loopback address, through its `listen` attribute and
every `<listen>` element; a network listen, a listen without an address and
a device with no listen are refused. The signature also counts the graphics
devices, so a second one is drift even on loopback. Every domain defined on
Nitro on 2026-10-05 (read with `virsh -r dumpxml --inactive`) listens on a
socket or on `127.0.0.1` and passes.

## Regression proof

`tests/graphics_exposure_contract.py` renders the domain template for a
standard and a VFIO Machine, checks the guard accepts both, and then gives
the guard a VNC device on every address, a second SPICE device, SPICE on a
libvirt network, on `0.0.0.0` and on `::`, a listen without an address, no
listen, and an RDP display: each is refused. Run against the previous
guard, the contract fails on the first case.
