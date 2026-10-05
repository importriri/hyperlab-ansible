# ADR 0041 - Seamless guest applications

Status: proposed. Future work in the roadmap ("Later"); this decides the
shape before any code. HyperLab does not provide Qubes OS security
properties, and seamless applications would not either.

## Context

Today a Machine is a whole desktop: Looking Glass for VFIO Machines, the
SPICE console for the others. Seamless applications would put one guest
application's window on the host desktop, beside host windows and other
Machines' windows. Three rules decide the shape:

- the host names every surface: a guest window must carry its Machine's
  provenance from the host's own knowledge, never from what the guest says;
- data crosses only through an explicit host action: a seamless window must
  not bring a clipboard, drag and drop or file transfer of its own;
- whatever parses the guest's stream on the host is new attack surface on
  the control plane.

## Options

**A. Waypipe per application over the pinned SSH channel (recommended
for Linux).** The host starts `waypipe ssh` to the Machine for one
application; the window's host process is the waypipe client the host
started for that Machine, so the focused-surface resolver maps it to the
Machine by PID, like the Looking Glass client. Before it ships: the waypipe
client runs confined (its own user or a bubblewrap sandbox with no access
but its Wayland socket), and the clipboard and drag-and-drop protocols are
not forwarded, which needs a proxy that drops `wl_data_device` and
`zwp_primary_selection` or a waypipe option to that effect, proved by a
test.

**B. RDP RemoteApp for Windows Machines.** FreeRDP's RAIL mode shows single
Windows applications; the same rules apply: clipboard, drives and devices
off, the client confined and mapped by PID.

**C. Stay with whole desktops.** No new parser on the host; the Machine is
always one window with one frame.

## Recommendation

C until the host frame holds in every case (ADR 0039) and QEMU confinement
is decided (ADR 0037); then A for Linux Machines, with the confinement and
the clipboard filter proved first. B only if Windows Machines need it.
