# Nitro `arch-dev-vfio` campaign

`arch-dev-vfio` is the accelerated candidate. `arch-dev` remains unchanged as
the standard recovery workstation.

## Fixed boundaries

- libvirt connection: `qemu:///system`;
- domain: `arch-dev-vfio`;
- source spec: `vm-specs/arch-dev-vfio.yml`;
- resource profile selected once at creation: `balanced` (8 GiB) or `heavy`
  (16 GiB), both with four pinned vCPUs;
- reviewed Nitro pins: guest `2,6,3,7`, emulator `0,4`, disk I/O `1,5`;
- loopback SPICE and virtual VGA remain available until the campaign is sealed;
- the RTX 3060 display and audio functions move together;
- no persistent Linux Looking Glass sender service;
- hardware evidence is tied to the exact repository commit.

## Completed Nitro evidence

The host and guest acceptance work has already proved the VFIO attachment, CPU
plan, NVIDIA driver, kvmfr/IVSHMEM transport and real Looking Glass video path.
The managed Hyprland role also installs the NVIDIA-only Ly login hook and the
headless-output callback idempotently.

Do not repeat those investigations unless a later change touches the same
boundary or new evidence contradicts them.

## Revalidation order

Reconcile the host twice and require the final recap to report `changed=0`:

```bash
ansible-playbook -K -i inventory.ini playbooks/lab.yml --check --diff
ansible-playbook -K -i inventory.ini playbooks/lab.yml
ansible-playbook -K -i inventory.ini playbooks/lab.yml
```

Create `arch-dev-vfio` from the checked-in spec with one resource profile, then
keep that profile fixed for every lifecycle call. The first guest pass preserves
the stock recovery kernel while Zen is proven:

```bash
ansible-playbook -i /run/user/$UID/arch-dev-vfio.ini \
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
frames, input return, lock/unlock, reconnect and loopback SPICE recovery as
separate observations.

## Remaining acceptance

A fresh graphical session must still prove that `HEADLESS-0` appears without a
manual `hyprctl` command at `1920x1080@144`, scale `1`. After that:

1. persist deterministic XDPH selection of `HEADLESS-0`;
2. run the Linux Looking Glass sender manually;
3. confirm real frames on the physical-host client;
4. check keyboard and pointer return separately from video;
5. check lock/unlock and guest reboot/reconnect;
6. rerun the guest role and require `changed=0`;
7. retain sanitized logs and the final screenshot evidence.

The candidate is not a final compatibility result until those observations are
closed.
