# Service VM contract and recovery

M7 adds service ownership around the existing guest lifecycle. It does not
install application software on the hypervisor and it does not replace the
`guest` role.

## Sources of truth

A registered service is valid only when all three reviewed files agree:

1. `service-specs/<service>.yml` — service identity, reserved memory, lease,
   exposure intent and recovery policy;
2. `vm-specs/<service>.yml` — the permanent standard VM consumed by `guest`;
3. `group_vars/all/services.yml` — the unique static DHCP lease and global LAN
   exposure allowlist.

`tools/service_plan.py` rejects different names, RAM values, backup policies,
networks, MACs or IPs. The service MAC must also equal the deterministic MAC
that `guest_plan.py` derives from the VM name.

## Required order

Reconcile the persistent and active `services` network first, then register the
service before creating its VM:

```bash
ansible-playbook playbooks/network-domains.yml --check --diff
ansible-playbook playbooks/network-domains.yml \
  -e network_domains_restart_changed=true

ansible-playbook playbooks/service-register.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml
ansible-playbook playbooks/service-register.yml \
  -e service_spec=service-specs/svc-jellyfin.yml

ansible-playbook playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/svc-jellyfin.yml \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA... workstation"]}'
```

Registration refuses an existing libvirt domain, disk or managed VM state. This
prevents a receipt from claiming retroactive ownership of an unknown service.
Both the inactive and active libvirt network XML must contain exactly the
reviewed name/MAC/IP lease.

## Memory reservation

A root-owned service receipt reserves the VM's fixed memory even while the VM is
shut off. `guest` sums those inactive reservations before resolving any new VM
memory request. A service already visible in active `virsh domstats` is excluded
because libvirt already accounts for it; the candidate service is also excluded
from its own reservation during create or start.

The legacy per-laptop `services_reserved_mb` value stays zero. Service capacity
comes only from checked and individually revocable registration receipts.

## Exposure boundary

M7 opens no ports. `exposures` in the service spec must be a subset of
`service_lan_exposure_allowlist`, which is empty in this stage. M8 must add the
first reviewed entry and implement the matching firewall/NAT rule; an
application role may not create an ad-hoc host exposure.

## Offline backup

Backups require an explicit UTC identifier such as `20260728T050000Z` and a
libvirt domain state of `shut off`:

```bash
ansible-playbook playbooks/service-backup.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml \
  -e service_backup_id=20260728T050000Z
```

The role converts the permanent qcow2 into an independent qcow2 inside
`<backup-id>.new`, runs `qemu-img check`, records the service-spec, VM-spec and
service-receipt hashes, verifies the complete staged directory, then atomically
renames the directory. A backup ID is immutable and can never be overwritten.

## Restore and deletion

Restore is offline-only and requires the exact `<service>:<backup-id>`
confirmation:

```bash
ansible-playbook playbooks/service-restore.yml --check --diff \
  -e service_spec=service-specs/svc-jellyfin.yml \
  -e service_backup_id=20260728T050000Z \
  -e service_confirm_restore=svc-jellyfin:20260728T050000Z
```

The current disk moves to `.pre-restore`; the restored disk is committed and
checked before that rollback disk is removed. Any failure after the old disk is
preserved restores it automatically.

Backup deletion validates the backup again and requires the same exact
confirmation through `service_confirm_delete_backup`. Unregister requires the
exact service name and refuses until the libvirt domain, VM disk, managed VM
state and every backup have been removed.
