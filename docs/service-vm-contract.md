# Service VM contract and recovery

Service applications run inside standard VMs. The hypervisor owns registration,
network identity, capacity, exposure and recovery policy; it does not install the
application itself.

## Sources of truth

A registered service is valid only when these files agree:

1. `service-specs/<service>.yml`: identity, reserved memory, lease, exposure and
   recovery policy;
2. `vm-specs/<service>.yml`: permanent VM consumed by the guest lifecycle;
3. `group_vars/all/services.yml`: static DHCP lease and global exposure allowlist.

`tools/service_plan.py` rejects disagreement between service and VM identity,
memory, backup policy, network, MAC or IP. The service MAC must also match the
deterministic address derived from the VM name.

## Required order

Reconcile the `services` network, register the service, then create its VM:

```bash
ansible-playbook -K playbooks/network-domains.yml --check --diff
ansible-playbook -K playbooks/network-domains.yml \
  -e network_domains_restart_changed=true

ansible-playbook -K playbooks/service-register.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml
ansible-playbook -K playbooks/service-register.yml \
  -e service_spec=service-specs/svc-jellyfin.yml

ansible-playbook -K playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/svc-jellyfin.yml \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA... workstation"]}'
```

Registration refuses an existing domain, disk or managed VM state. A receipt
must never claim retroactive ownership of an unknown service.

## Capacity

A root-owned registration receipt reserves the service VM's fixed memory even
while it is stopped. The guest planner includes inactive reservations before it
accepts a new VM request, but does not count a service twice when libvirt already
reports it as active.

The old per-laptop `services_reserved_mb` value stays zero. Capacity comes from
individual service registrations that can be reviewed and revoked independently.

## LAN exposure

A service spec may request only endpoints present in the global exposure
allowlist. The host exposure role owns the matching nftables/libvirt hook state;
an application role may not open an ad-hoc host port.

Jellyfin is the current reference exposure. Its appliance document records the
single allowed endpoint and the negative boundary around the ports that remain
closed.

## Offline backup

Backups require a stopped domain and an explicit UTC identifier such as
`20260728T050000Z`:

```bash
ansible-playbook -K playbooks/service-backup.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml \
  -e service_backup_id=20260728T050000Z
```

The backup role builds an independent qcow2 in a staging directory, runs
`qemu-img check`, records the service/VM/receipt hashes, verifies the staged
result and only then commits the immutable backup directory.

## Restore and removal

Restore is offline-only and requires the exact `<service>:<backup-id>`
confirmation:

```bash
ansible-playbook -K playbooks/service-restore.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml \
  -e service_backup_id=20260728T050000Z \
  -e service_confirm_restore=svc-jellyfin:20260728T050000Z
```

The current disk is kept as a rollback copy until the restored disk has been
committed and checked. Backup deletion validates the backup again before removal.
Service unregister refuses while its domain, managed disk/state or backups still
exist.
