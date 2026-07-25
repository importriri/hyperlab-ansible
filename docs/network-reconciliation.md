# Libvirt network reconciliation

The role renders all five desired persistent XML definitions and compares the
managed semantic fields against `virsh net-dumpxml --inactive`. Missing and
changed definitions are both reconciled; this fixes the old create-only
behaviour that left existing networks stale forever.

Changing an active bridge is disruptive. The role therefore fails closed and
prints the maintenance-window command:

```bash
ansible-playbook playbooks/lab.yml -e network_domains_restart_changed=true
```

That opt-in stops only changed active networks, redefines them, starts them and
restores autostart. Unchanged networks remain untouched, preserving second-run
idempotence.
