# Nitro `arch-dev-vfio` campaign

`arch-dev-vfio` is the accelerated candidate. `arch-dev` remains unchanged as
the standard recovery workstation.

## Fixed boundaries

- libvirt connection: `qemu:///system`;
- domain: `arch-dev-vfio`;
- source spec: `vm-specs/arch-dev-vfio.yml`;
- checked-in resource profile: `heavy`, 16 GiB and four pinned vCPUs;
- checked-in virtual disk size: 100 GiB;
- reviewed Nitro pins: guest `2,6,3,7`, emulator `0,4`, disk I/O `1,5`;
- a private per-domain SPICE UNIX socket and virtual VGA remain available until the campaign is sealed;
- the RTX 3060 display and audio functions move together;
- an ICH9 duplex device maps guest playback and capture to the private SPICE
  audio backend; the passed HDMI function is not the laptop-speaker path;
- no persistent Linux Looking Glass sender service;
- hardware evidence is tied to the exact repository commit.

## Completed Nitro evidence

The host and guest acceptance work has already proved the VFIO attachment, CPU
plan, NVIDIA driver, kvmfr/IVSHMEM transport and real Looking Glass video path.
The managed Hyprland role also installs the NVIDIA-only Ly login hook and the
headless-output callback idempotently. A fresh graphical login produced the
managed `HEADLESS-0` automatically at `1920x1080@144`, scale `1`, and a
1920x1080 `grim` capture of the guest lock screen.

Do not repeat those investigations unless a later change touches the same
boundary or new evidence contradicts them.

## Revalidation order

Reconcile the host twice and require the final recap to report `changed=0`:

```bash
ansible-playbook -K -i inventory.ini playbooks/lab.yml --check --diff
ansible-playbook -K -i inventory.ini playbooks/lab.yml
ansible-playbook -K -i inventory.ini playbooks/lab.yml
```

Create `arch-dev-vfio` from the checked-in spec. Existing 8 GiB/24 GiB campaign
domains first run the managed disk expansion with an explicit `balanced` source
profile, then the offline reconfiguration transaction to commit `heavy` and the
current device XML. The first guest pass preserves the stock recovery kernel
while Zen is proven:

```bash
ansible-playbook -K playbooks/vm-resize-disk.yml \
  -e guest_spec=vm-specs/arch-dev-vfio.yml \
  -e guest_resource_profile=balanced \
  -e guest_confirm_resize=arch-dev-vfio

ansible-playbook -K playbooks/vm-reconfigure.yml \
  -e guest_spec=vm-specs/arch-dev-vfio.yml \
  -e guest_confirm_reconfigure=arch-dev-vfio
```

```bash
ansible-playbook -K playbooks/vm-guest-inventory.yml \
  -e guest_spec=vm-specs/arch-dev-vfio.yml

ansible-playbook -i inventory.ini \
  -i /run/user/$UID/arch-dev-vfio.ini \
  playbooks/guest-arch-dev.yml \
  -e admin_user=sid \
  -e workstation_kernel_profile=arch-zen \
  -e workstation_kernel_remove_fallback=false
```

After the guest boots Zen and both NVIDIA PCI functions are visible, apply
`playbooks/guest-arch-dev-vfio.yml` twice. The second pass must report
`changed=0`. The host and guest read-only gates must then emit:

```text
ARCH_DEV_VFIO_HOST_GATE_OK
ARCH_DEV_VFIO_GUEST_GATE_OK
```

Apply `playbooks/guest-visual-assets.yml` only after the guest role is green and
rerun the asset transaction for idempotence. Start the Linux Looking Glass sender
manually from the Hyprland session. Do not create a systemd sender unit; capture
frames, input return, lock/unlock, reconnect and UNIX-socket SPICE recovery as
separate observations.

## Remaining acceptance

A fresh graphical session has proved that `HEADLESS-0` appears without a manual
`hyprctl` command at `1920x1080@144`, scale `1`. The opt-in sender role now
persists a deterministic XDPH picker for that exact output. The remaining
observations are:

1. apply the picker and require a second guest pass with `changed=0`;
2. run the Linux Looking Glass sender manually;
3. confirm real frames on the physical-host client;
4. check keyboard and pointer return separately from video;
5. check lock/unlock and guest reboot/reconnect;
6. retain sanitized logs and the final screenshot evidence.
7. verify guest playback through SPICE and confirm host volume steps can reach
   the reviewed 125 percent software ceiling without clipping.

The candidate is not a final compatibility result until those observations are
closed.

## Performance and security acceptance

The accelerated Arch workshop is not sealed until performance work is measured
against the fixed host security floor described in
[`performance-security-contract.md`](performance-security-contract.md).

The Nitro Secure Boot transition is tracked separately in
[`nitro-secure-boot-acceptance.md`](nitro-secure-boot-acceptance.md). The
current machine has completed preparation and non-writing enrollment previews;
real firmware enrollment, module-trust review and the post-boot hardware proof
remain open.

Gaming work follows this order:

1. freeze the final security baseline;
2. measure the current 4-vCPU/NVIDIA/Looking Glass baseline;
3. add transactional host/guest Gaming Mode;
4. compare CPU isolation and EPP policy;
5. complete the guest gaming stack and frame-time telemetry;
6. compare alternate guest kernels and memory policies only when measurable;
7. compare the reviewed 4-vCPU and 6-vCPU plans;
8. reject any optimization that weakens the security floor.

The campaign records rejected experiments as deliberately as accepted ones.
