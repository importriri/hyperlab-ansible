# The first Machine from a Template

This is the whole chain on Nitro, once, by hand:

```text
sealed Golden Image  arch-dev-20261003   images/arch-dev-20261003.yml
  -> Template        workstation-dev     templates/workstation-dev.yml
  -> Machine         dev-01              ~/.local/state/hyperlab/machines/dev-01.yml
  -> VM spec         dev-01              vm-specs/.generated/dev-01.yml (derived, not in Git)
  -> domain          dev-01              libvirt, created by vm-create.yml
```

The shell's Create view runs the same steps: **Machines → New Machine**
records and projects the Machine, then one operation window runs every
`ansible-playbook` command of steps 2 and 3 below (for a server, those of
"A server Machine"), in the same order with the same arguments, asking for
your password for each `-K` playbook and, for a workstation, for the
Machine account's password
([ADR 0017](adr/0017-shell-machine-creation.md)). The `ansible -m ping`
check of the server section is yours to run. Before the first step, the
operation refuses a Machine whose generated spec is not exactly the
projection of its record (edited by hand, even only from `2048` to
`2048.0`, a link, unreadable or missing) and a plan with any playbook that
is not the reviewed one, present as a regular file in `playbooks/`; the
profile it accepts is the one the Machine record's Template maps to. It
then runs nothing and asks for nothing.
If a step fails, the operation stops there and ends `failed` with that
step's exit status. The Machine record and its spec stay: a failed
provisioning is not a refused creation, and the remaining steps are the
commands below. By hand they are these commands.

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
with the key, sets the host's time zone, and the guest generates a new
machine-id and SSH host keys.

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
ansible-playbook -i inventory.ini -i /run/user/$UID/dev-01.ini \
  playbooks/guest-close-access.yml
```

`openssl passwd -6` asks twice without echo and prints only the hash.

The last step closes the provisioning access. The QEMU Guest Agent then
answers only the calls HyperLab uses (no `guest-exec`), and, since the
account now has a password, cloud-init's passwordless sudo rule is removed:
later profile passes need `-K` and the Machine account's password. The step
proves from the host that `guest-exec` is refused and that the host key read
through the agent is still the pinned one.

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
ansible-playbook -i inventory.ini -i /run/user/$UID/srv-01.ini \
  playbooks/guest-close-access.yml
```

A server account has no password, so the last step restricts the guest
agent and keeps its passwordless sudo: removing it would leave the Machine
without administration.

The inventory step pins the new host key, so plain `ssh` to the address it
wrote works with strict checking too.

`--lifecycle disposable` makes a server Machine that forgets everything it
wrote whenever it stops ([ADR 0018](adr/0018-disposable-discards-on-stop.md)).
Every start is a first boot with new SSH host keys, so run the inventory
step again after each start to pin the new key.

## 4. Looking at it

```bash
hyperlabctl open looking-glass dev-01
```

Expected: the dev wallpaper and theme, the Workspace Shell, `ALT+1`…`ALT+9`
moving between Desks, `ALT+H` showing the key sheet.
