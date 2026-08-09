# Jellyfin reference appliance

Jellyfin is the reference service VM. The application runs only inside
`svc-jellyfin`; the physical hypervisor installs no Jellyfin package and does not
serve Jellyfin itself.

## Prerequisites

Before running the appliance playbook:

1. the reviewed Debian base image is sealed and validates;
2. `svc-jellyfin` has a valid service registration receipt;
3. the VM exists from `vm-specs/svc-jellyfin.yml`;
4. the active and persistent `services` network contain the reviewed static lease;
5. every libvirt domain is stopped when the host exposure hook contract is first
   installed or changed.

Run:

```bash
ansible-playbook -K playbooks/jellyfin.yml --check --diff
ansible-playbook -K playbooks/jellyfin.yml
```

The host-side part validates registration, installs the managed exposure hook and
starts the service through the normal guest lifecycle. Guest configuration waits
for SSH, checks the Debian identity and installs Jellyfin inside the VM.

## Package provenance

The guest uses Debian `extrepo`, enables only the Jellyfin repository definition
and requires a dedicated `Signed-By` key for `repo.jellyfin.org`. The role does
not run a downloaded shell script as root and refuses Docker or Podman on this
appliance.

The `jellyfin` metapackage must install both server and web components. The role
starts `jellyfin.service`, waits for `127.0.0.1:8096` and requires an HTTP 200
response from `/web/index.html`.

First-run administration, accounts and library choices stay outside Git.
`/srv/media` is `root:jellyfin` mode `0750`; the service can read/traverse the
media root but cannot write to it.

## LAN exposure

The reviewed service allows only `tcp/8096`. HTTPS 8920, discovery 7359/UDP,
DLNA ports and future endpoints remain closed until they receive their own
reviewed policy.

The exposure role derives one physical/default-route interface. Multiple default
routes fail closed unless the operator selects a reviewed interface that is
already one of the observed defaults. Loopback, libvirt bridges, taps, tunnels
and container bridges are refused.

The libvirt `qemu.d` hook creates runtime exposure state only while
`svc-jellyfin` is active. It manages its own nftables table and rules identified
by the `privatestack-service-exposure:` comment prefix. It never flushes the
whole ruleset. A failed apply removes its own partial state and prevents the VM
start from being treated as successful.

## Validation and recovery

Inside the service VM:

```bash
systemctl is-active jellyfin.service
curl --fail http://127.0.0.1:8096/web/index.html
```

From a LAN client during the hardware gate:

```bash
curl --fail http://<hypervisor-lan-address>:8096/web/index.html
```

Backup and restore use the normal offline service transaction documented in
[`service-vm-contract.md`](service-vm-contract.md). Application configuration and
metadata live on the permanent service disk and follow that same recovery path.
