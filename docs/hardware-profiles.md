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
