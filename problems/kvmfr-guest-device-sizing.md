# kvmfr host sizing was mistaken for guest configuration

Author: [importriri](https://github.com/importriri).

## Symptom

It was tempting to mirror the host `static_size_mb` module setting inside the
Linux guest because both sides expose `/dev/kvmfr0`. That would have described
two different mechanisms as if they were the same one.

## What was wrong

On the physical host, kvmfr allocates the shared-memory backing used by libvirt.
Inside the guest, the device is created from the `1af4:1110` IVSHMEM PCI
function. The guest must not allocate a second static region.

## Fix

Keep `static_size_mb` as host policy only. The guest role loads kvmfr, applies
permissions to the IVSHMEM-backed device and explicitly refuses a guest
`static_size_mb` configuration.

## Regression proof

The guest exposed `/dev/kvmfr0` without a guest modprobe size override, the guest
user had read/write access, and the Looking Glass sender transported real frames
through that device.
