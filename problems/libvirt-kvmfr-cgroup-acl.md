# QEMU still could not open kvmfr after the device permissions were correct

Author: [importriri](https://github.com/importriri).

## Symptom

The host kvmfr character device existed with the expected ownership, yet the
confined QEMU process could still be denied when opening it. Unix mode bits were
not the whole access path.

## What was wrong

libvirt's QEMU device policy can restrict character devices independently of
filesystem permissions. Adding kvmfr carelessly to an explicit ACL is also
dangerous: replacing the implicit default with an incomplete list can remove
QEMU access to core devices such as `/dev/kvm`.

## Fix

Manage one explicit libvirt device ACL only after proving there is no unknown
administrator-owned ACL. Build it from the required QEMU character devices,
available optional devices and the managed kvmfr node, then reload libvirt.

## Regression proof

The role has a structural contract for the required device set, refusal of an
unmanaged ACL and the libvirt reload handler. Nitro VFIO validation subsequently
used the real kvmfr-backed domain.
