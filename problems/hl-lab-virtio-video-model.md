# The lab host asked for a display device Nitro's QEMU does not have

Author: [importriri](https://github.com/importriri).

Status: corrected; covered by `tests/hl_lab_contract.py`.

## Symptom

`tools/lab/hl_lab.py create` on Nitro made the volumes, then libvirt refused
the domain:

```text
error: unsupported configuration: domain configuration does not support video model 'virtio'
```

## Cause

The lab host's template asked for a `virtio` video device. Arch splits
QEMU's display devices into modules, and Nitro has `qemu-base` without the
virtio-gpu module; every Machine uses `vga`, which the base provides.
Schema validation (`virt-xml-validate`) and the contract's checks passed,
since the model is valid libvirt XML: only the host's QEMU decides.

## Fix

The lab host uses the Machines' model, `vga` with 16 MiB of video memory.

## Regression proof

The contract requires the lab host's video model to be the one the Machine
domain template uses, which the host's QEMU provides for every Machine.
Against the previous template it fails.
