# Linux ISO workshop

`image_factory` seals qcow2 bases; it never treats installer ISO media as a
bootable base. Distributions without an official cloud qcow2 therefore use a
small manual workshop and enter the factory as `source_type: local`.

Parrot is the first reviewed example.

## Build boundary

1. Download the official ISO and its published checksum outside the repository.
2. Verify that checksum independently.
3. Create an unmanaged temporary VM with virt-manager or `virt-install`.
4. Keep its qcow2 outside `/var/lib/libvirt/images`.
5. Install the distribution, QEMU Guest Agent and current updates.
6. Keep the Parrot workshop on the isolated `lab` network.
7. Shut down cleanly and verify the source has no backing file.
8. Hash the resulting qcow2 independently.
9. Import it through the same local transaction used by other private workshop
   outputs.

Example:

```bash
qemu-img info --output=json /private/workshop/parrot.qcow2
sha256sum /private/workshop/parrot.qcow2

ansible-playbook -K playbooks/image-prepare.yml --check --diff \
  -e image_factory_manifest=images/parrot.yml \
  -e image_factory_local_source=/private/workshop/parrot.qcow2 \
  -e image_factory_source_sha256=<source-sha256>
```

Repeat the real apply and then `image-validate.yml`. Commit the sealed artifact
hash and source hash printed by the factory before using
`vm-specs/parrot-disposable.yml`.

The ISO and installed source remain local. The public manifest records the
transaction policy and hashes, not redistributable installation media.
