# Physical host profiles and compatibility evidence

`host_profile` selects the physical laptop. It is intentionally different
from a VM `device_profile` (`standard` or `vfio`): one answers *which machine
is running Ansible*, the other answers *which virtual hardware a guest gets*.
Reusing one key for both would let a VM spec overwrite laptop selection.

The public pipeline does not ask users to edit a raw `vfio-pci.ids=` string.
`hardware_probe` reads numeric PCI identities, selects one complete reviewed
host profile, and refuses an absent or ambiguous automatic match. An explicit
unknown profile keeps its own error and is never masked as unknown hardware.

Known component profiles:

- `nitro-3060`: `10de:2520` + `10de:228e`
- `predator-3070`: `10de:249d` + `10de:228b`

Run `ansible-playbook -K playbooks/preflight.yml` first. The local report records,
without DMI serial numbers:

- selected `host_profile` and label;
- ordered VFIO ID-to-PCI-address records;
- GPU and GPU-audio PCI addresses;
- detected CPU thread count;
- the complete detected numeric PCI-ID set.

The public profile leaves evidence fields null until a real report is reviewed;
addresses are collected, never guessed. A new laptop is added only after that
report and the validation checklist in `arch-hypervisor-lab/hardware/` have
been reviewed. Component-level success is not called a full pipeline pass.

## Nitro VFIO CPU isolation

The reviewed i5-10300H topology has four physical cores with sibling pairs
`0/4`, `1/5`, `2/6` and `3/7`. VFIO rendering selects a plan by the guest vCPU
count and refuses it unless preflight still reports eight host threads.

The four-vCPU plan gives complete sibling pairs `2/6` and `3/7` to the guest,
keeps `0/4` for QEMU emulation and the host control plane, and assigns `1/5` to
the disk I/O thread. This is the preferred interactive Linux workstation plan.

The six-vCPU plan gives `1/5`, `2/6` and `3/7` to the guest while QEMU emulation
and I/O share `0/4`. It exists for reviewed Windows benchmark workloads; it is
not the default for `arch-dev` because the host-side display client still needs
predictable CPU time.

Both plans render `host-passthrough`, explicit libvirt vCPU pins, emulator and
I/O-thread pins, a matching virtual topology and one disk I/O thread. PCI
addresses remain host-local evidence and are never copied into public profiles.
