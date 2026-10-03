# The first Machine from a Template

This is the whole chain on Nitro, once, by hand:

```text
sealed Golden Image  arch-dev-20261003   images/arch-dev-20261003.yml
  -> Template        workstation-dev     templates/workstation-dev.yml
  -> Machine         dev-01              ~/.local/state/hyperlab/machines/dev-01.yml
  -> VM spec         dev-01              vm-specs/.generated/dev-01.yml (derived, not in Git)
  -> domain          dev-01              libvirt, created by vm-create.yml
```

The shell's Create view will run the same steps; until then they are
commands.

## Before

- `arch-dev-vfio` is shut off: there is one GPU and one Looking Glass
  device. Both domains may name the GPU; only one may run with it
  ([ADR 0016](adr/0016-gpu-shared-definition-running-lease.md)).
- In this host boot the GPU has not yet gone to a `dirty` or `lab` Machine;
  the ladder never lets it climb back to `dev`.
- The SSH public key you use for guests, here `~/.ssh/hyperlab_ed25519.pub`.
  cloud-init gives it to the account `sid` of the new Machine.

## 1. The Machine

```bash
hyperlabctl machine templates
hyperlabctl machine create workstation-dev dev-01 \
  --display-name "Dev 01" --looking-glass-mode linux-experimental
hyperlabctl machine project dev-01
```

`create` only records intent outside Git: Template version, image id and
digest, network, GPU class, resources. `project` writes the derived VM spec,
pinned to the same digest; it refuses if the image was sealed again since.

## 2. The domain

```bash
ansible-playbook -K playbooks/vm-create.yml \
  -e guest_spec=vm-specs/.generated/dev-01.yml \
  -e guest_start_after_create=true \
  -e "{\"guest_cloud_init_ssh_public_keys\":[\"$(command cat ~/.ssh/hyperlab_ed25519.pub)\"]}"
```

A permanent Machine gets an independent copy of the sealed base, so later
changes to the store never reach it and the base is never written. On first boot cloud-init names the Machine `dev-01`, creates `sid`
with the key, and the guest generates a new machine-id and SSH host keys.

## 3. The rice

```bash
ansible-playbook -K playbooks/vm-guest-inventory.yml \
  -e guest_spec=vm-specs/.generated/dev-01.yml
ansible-playbook -i inventory.ini -i /run/user/$UID/dev-01.ini \
  playbooks/guest-arch-dev-vfio.yml
ansible-playbook -i inventory.ini -i /run/user/$UID/dev-01.ini \
  playbooks/guest-arch-dev-vfio.yml
```

The dev profile playbook is the one that built `arch-dev-vfio`. Every
package is already in the image, so the first pass mostly configures the new
account; the second must report `changed=0`.

## 4. Looking at it

```bash
hyperlabctl open looking-glass dev-01
```

Expected: the dev wallpaper and theme, the Workspace Shell, `ALT+1`…`ALT+9`
moving between Desks, `ALT+H` showing the key sheet.
