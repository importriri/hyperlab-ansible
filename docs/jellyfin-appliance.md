# Jellyfin reference appliance

M8 promotes the registered `svc-jellyfin` contract into the first complete
application VM. Jellyfin runs only inside the Debian service VM. The hypervisor
installs no Jellyfin package and opens no listening socket of its own.

## Prerequisites

Before running the application playbook:

1. the Debian base image is sealed and its M5 receipt validates;
2. `svc-jellyfin` is registered through M7;
3. the VM has been created from `vm-specs/svc-jellyfin.yml`;
4. the persistent and active `services` network contain the reviewed lease
   `52:54:00:66:29:6e` / `10.10.5.10`;
5. every libvirt domain is stopped for the first hook installation or for any
   later hook-contract update.

The application orchestration is:

```bash
ansible-playbook -K playbooks/jellyfin.yml --check --diff
ansible-playbook -K playbooks/jellyfin.yml
```

The first play validates the M7 receipt, installs the host exposure hook and
starts the registered VM through the existing guest lifecycle. The second play
waits for SSH, verifies the Debian 12 hostname/address identity and configures
Jellyfin inside the guest.

## Package provenance

The guest installs Debian's `extrepo` package, enables only the `jellyfin`
repository definition and requires that its source points to
`repo.jellyfin.org` with a dedicated `Signed-By` key. The role never executes a
remote script as root and refuses Docker or Podman on this appliance.

The `jellyfin` metapackage must install `jellyfin-server` and `jellyfin-web`.
The role starts `jellyfin.service`, waits for `127.0.0.1:8096` and requires an
HTTP 200 response from `/web/index.html`.

Interactive first-run administration, library paths and user accounts remain
outside Git. `/srv/media` is created as `root:jellyfin` mode `0750`; Jellyfin
receives read/traverse access but cannot write into the media root.

## LAN exposure

M8 permits exactly `tcp/8096`. HTTPS 8920, discovery 7359/UDP, DLNA ports and
all future service endpoints remain closed.

`service_exposure` derives one physical/default-route interface from
`ip -j -4 route show default`. Multiple defaults fail closed unless the operator
sets a reviewed override that is itself one of the observed defaults. Loopback,
libvirt bridges, taps, tunnels and container bridges are refused.

The libvirt `qemu.d` hook creates a runtime marker only while `svc-jellyfin` is
active. Reconciliation owns:

- table `ip privatestack_services`, containing the DNAT rule from LAN port 8096
  to `10.10.5.10:8096`;
- rules in `ip libvirt_network guest_input` whose comments begin with the exact
  `privatestack-service-exposure:` prefix.

It never flushes the nftables ruleset and deletes only handles with that prefix.
If rule application fails, it removes its own partial table/rules and the VM
start fails closed. On `stopped` or `release`, the marker and exposure disappear.

## Validation and recovery

Inside the guest:

```bash
systemctl is-active jellyfin.service
curl --fail http://127.0.0.1:8096/web/index.html
```

From a LAN client during the final hardware campaign:

```bash
curl --fail http://<hypervisor-lan-address>:8096/web/index.html
```

A service backup remains the M7 offline qcow2 backup. Shut down the VM cleanly,
create an immutable backup, and restore only with the exact confirmation string.
Application configuration and media metadata live on the permanent service disk
and therefore follow the same verified backup/restore transaction.
