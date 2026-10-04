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

Resources come from the Template's profiles (`balanced` by default). To
choose them yourself:

```bash
hyperlabctl machine create workstation-dev dev-02 \
  --looking-glass-mode linux-experimental \
  --resource-profile custom --memory-mb 24576 --vcpus 6 --disk-gib 200
```

The disk can never be smaller than the image (100 GiB here); memory is
checked against the live host budget when the domain is created.

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

cloud-init creates `sid` with a locked password: only the SSH key works. A
workstation needs a password for the lock screen and the console, so the
first pass takes it as a SHA-512 hash from a file that lives only in memory
and is deleted after the run:

```bash
ansible-playbook -K playbooks/vm-guest-inventory.yml \
  -e guest_spec=vm-specs/.generated/dev-01.yml
umask 077
H=$(openssl passwd -6) && printf "workstation_access_password_hash: '%s'\n" "$H" \
  > /run/user/$UID/dev-01-access.yml; unset H
ansible-playbook -i inventory.ini -i /run/user/$UID/dev-01.ini \
  playbooks/guest-arch-dev-vfio.yml -e @/run/user/$UID/dev-01-access.yml
rm -v /run/user/$UID/dev-01-access.yml
ansible-playbook -i inventory.ini -i /run/user/$UID/dev-01.ini \
  playbooks/guest-arch-dev-vfio.yml
```

`openssl passwd -6` asks twice without echo and prints only the hash. Later
passes need no password: the account is already usable.

The inventory step also reads the new Machine's SSH host key through QEMU
Guest Agent and pins it in `~/.ssh/known_hosts` for its address, so the
strict SSH check never trusts a key shown on the network.

The dev profile playbook is the one that built `arch-dev-vfio`. Every
package is already in the image, so the first pass mostly configures the new
account; the second must report `changed=0`.

## A server Machine

`server-arch` gives a headless Arch Machine reached over SSH only, from the
sealed upstream Arch image. There is no rice to apply:

```bash
hyperlabctl machine create server-arch srv-01 \
  --resource-profile custom --memory-mb 2048 --vcpus 2 --disk-gib 16
hyperlabctl machine project srv-01
ansible-playbook -K playbooks/vm-create.yml \
  -e guest_spec=vm-specs/.generated/srv-01.yml \
  -e guest_start_after_create=true \
  -e "{\"guest_cloud_init_ssh_public_keys\":[\"$(command cat ~/.ssh/hyperlab_ed25519.pub)\"]}"
ansible-playbook -K playbooks/vm-guest-inventory.yml \
  -e guest_spec=vm-specs/.generated/srv-01.yml
ansible srv-01 -i inventory.ini -i /run/user/$UID/srv-01.ini -m ping
```

The inventory step pins the new host key, so plain `ssh` to the address it
wrote works with strict checking too.

## 4. Looking at it

```bash
hyperlabctl open looking-glass dev-01
```

Expected: the dev wallpaper and theme, the Workspace Shell, `ALT+1`…`ALT+9`
moving between Desks, `ALT+H` showing the key sheet.
