# The host's internal PC speaker beeped

Reported by the operator on 2026-10-13: the Nitro beeped from its internal
speaker the evening before. `lsmod` on the host shows `pcspkr` loaded;
`/etc/modprobe.d` has no rule for it, so the kernel loads it at every boot
from the platform device's alias (`platform:pcspkr`).

## Fix

The base role installs `/etc/modprobe.d/hyperlab-pc-speaker.conf`
(root:root 0644), which blacklists `pcspkr` and `snd_pcsp`, the two PC
speaker drivers. It then unloads whichever of them is loaded, so the beep
stops without a reboot. Nothing in HyperLab uses the PC speaker; sound goes
through the sound card.

A driver counts as loaded when `/sys/module/NAME/initstate` exists, and is
unloaded with `rmmod`. The first version used the modprobe module, found
in review: it reads the running kernel's module tree, which Arch removes on
a kernel upgrade until the next boot, so `foundation.yml` would have
stopped at base in that window, in check mode too. A driver still in use
is reported and stays loaded until the next boot; that is not a failure.

## Regression proof

`tests/base_pc_speaker_contract.py` requires the file, its owner and mode,
exactly those two blacklist lines, the read from `/sys/module`, and `rmmod`
of exactly the loaded drivers, never stopping the role; where modprobe is
installed and the system does not already blacklist both, it has modprobe
parse the file (`modprobe -C FILE --showconfig`) and find both lines.
Against the previous role: `the base role installs no PC speaker blacklist
in /etc/modprobe.d`. Against the first version: `the base role unloads with
modprobe, which fails without the running kernel's module tree`.

## Not covered

A blacklist stops loading by alias only: a command that asks for the module
by name (`modprobe pcspkr`, as root) still loads it.
