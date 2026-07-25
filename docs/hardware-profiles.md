# Hardware profiles and compatibility evidence

The public pipeline does not ask users to edit a raw `vfio-pci.ids=` string.
`hardware_probe` reads numeric PCI identities, selects one complete known
profile, and refuses an absent or ambiguous match. The validated IDs are then
passed to `vfio_boot` and recorded locally without DMI serial numbers.

Known component profiles:

- `nitro-3060`: `10de:2520` + `10de:228e`
- `predator-3070`: `10de:249d` + `10de:228b`

Run `ansible-playbook playbooks/preflight.yml` first. A new laptop is added only
after its report and the complete validation checklist in
`arch-hypervisor-lab/hardware/` have been reviewed. Component-level success is
not called a full pipeline pass.
