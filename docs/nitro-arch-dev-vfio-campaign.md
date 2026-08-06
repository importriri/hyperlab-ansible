# Nitro `arch-dev-vfio` hardware campaign

This runbook starts only after the ten local preparation commits pass the
repository verification battery. It creates a separate accelerated candidate;
`arch-dev` remains the proven SPICE recovery workstation and is never converted
in place.

## Campaign invariants

- libvirt connection: `qemu:///system`;
- candidate domain: `arch-dev-vfio`;
- source spec: `vm-specs/arch-dev-vfio.yml`;
- resource profile selected once at creation: `balanced` (8 GiB) or `heavy`
  (16 GiB), both with four pinned vCPUs;
- reviewed Nitro pins: guest `2,6,3,7`, emulator `0,4`, disk I/O `1,5`;
- loopback SPICE and virtual VGA stay present until the campaign is sealed;
- no persistent Linux Looking Glass sender service is permitted;
- the existing `arch-dev` domain and disk are not modified.

## 1. Reconcile the physical host

Run the normal host pipeline first and require an idempotent second pass:

```bash
ansible-playbook -K -i inventory.ini playbooks/lab.yml --check --diff
ansible-playbook -K -i inventory.ini playbooks/lab.yml
ansible-playbook -K -i inventory.ini playbooks/lab.yml
```

The final recap must report `changed=0`. Confirm that the hardware report still
selects `nitro-3060`, records eight CPU threads and names both reviewed NVIDIA
PCI functions.

## 2. Create the isolated VFIO candidate

Choose exactly one profile for this candidate. The balanced example is:

```bash
ansible-playbook -K -i inventory.ini playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/arch-dev-vfio.yml \
  -e guest_resource_profile=balanced \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'

ansible-playbook -K -i inventory.ini playbooks/vm-create.yml \
  -e guest_spec=vm-specs/arch-dev-vfio.yml \
  -e guest_resource_profile=balanced \
  -e '{"guest_cloud_init_ssh_public_keys":["ssh-ed25519 AAAA..."]}'

ansible-playbook -K -i inventory.ini playbooks/vm-start.yml \
  -e guest_spec=vm-specs/arch-dev-vfio.yml \
  -e guest_resource_profile=balanced
```

Replace `balanced` with `heavy` consistently to create the 16 GiB candidate.
Do not change the profile on later lifecycle calls; the managed state binds the
creation choice and refuses silent resource drift.

## 3. Stage the Zen workstation before NVIDIA

Discover the candidate address through QEMU Guest Agent or the Dev-domain lease,
then create a temporary workstation inventory outside Git. The first guest pass
keeps the stock kernel only as a boot fallback while installing Zen, Hyprland and
the development stack:

```bash
ansible-playbook -i /run/user/$UID/arch-dev-vfio.ini \
  playbooks/guest-arch-dev.yml \
  -e admin_user=sid \
  -e workstation_kernel_profile=arch-zen \
  -e workstation_kernel_remove_fallback=false
```

Use the managed shutdown and start playbooks, then prove the guest booted a Zen
kernel. Rerun `guest-arch-dev.yml` without the fallback override; this removes
the stock kernel only after the running Zen kernel is proven.

## 4. Install the passed-GPU stack

With both NVIDIA PCI functions visible inside the Zen guest, apply the complete
accelerated workstation playbook twice:

```bash
ansible-playbook -i /run/user/$UID/arch-dev-vfio.ini \
  playbooks/guest-arch-dev-vfio.yml \
  -e admin_user=sid \
  -e workstation_kernel_profile=arch-zen

ansible-playbook -i /run/user/$UID/arch-dev-vfio.ini \
  playbooks/guest-arch-dev-vfio.yml \
  -e admin_user=sid \
  -e workstation_kernel_profile=arch-zen
```

The second recap must report `changed=0`. Perform another managed shutdown and
start so the open NVIDIA module set, DRM parameters and regenerated initramfs
are tested from a clean boot.

## 5. Run the read-only acceptance gates

On the physical Nitro host:

```bash
sudo tools/nitro/arch_dev_vfio_host_gate.py
```

Inside the guest, as `sid`, from its repository checkout:

```bash
tools/nitro/arch_dev_vfio_guest_gate.py
```

Required markers:

```text
ARCH_DEV_VFIO_HOST_GATE_OK
ARCH_DEV_VFIO_GUEST_GATE_OK
```

A refusal is evidence, not a prompt to bypass the contract. Preserve the full
output and repair the checked-in profile or role before retrying.

## 6. Inject private wallpaper assets

After the Hyprland role is green, inject the reviewed private bundle. The
controller and remote staging copies are deleted by the role; only the installed
pools remain in the guest:

```bash
ansible-playbook -i /run/user/$UID/arch-dev-vfio.ini \
  playbooks/guest-visual-assets.yml \
  -e guest_visual_assets_bundle_url=https://assets.example/private.tar.zst \
  -e guest_visual_assets_bundle_sha256=<reviewed-lowercase-sha256>
```

Rerun the same transaction and require `changed=0`.

## 7. Interactive Linux Looking Glass gate

Start `looking-glass-host` manually from the active Hyprland session. Record:

1. the portal source selection and the chosen monitor;
2. first frame and sustained frame production;
3. resolution changes and fullscreen behaviour;
4. keyboard and pointer return paths;
5. Hyprlock lock and unlock;
6. guest reboot and reconnect;
7. recovery through loopback SPICE after the sender is stopped.

Then launch the already configured physical-host Looking Glass client and retain
both sender and client logs. Do not create a systemd sender unit. A fork decision
is made only from this evidence and is limited to the Linux capture/input side;
the upstream LGMP, kvmfr and client contracts remain the compatibility target.

## 8. Seal or refuse

The candidate is sealable only when both automated markers, the manual checklist,
a post-reboot idempotent guest pass and SPICE recovery are green. Otherwise keep
`arch-dev-vfio` as an experimental candidate and leave `arch-dev` untouched.
