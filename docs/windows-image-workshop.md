# Windows image workshop

The Windows workshop is the one deliberate manual boundary in the managed VM
pipeline. `virt-manager` is used only to install and prepare a temporary source
VM. It is **not** the lifecycle manager for the final HyperLab domains.

Run this procedure only after the same frozen `arch-bootstrap` and
`hyperlab-ansible` candidates have completed:

1. clean Arch installation and two successful Hardened boots;
2. `foundation.yml` convergence and an immediate `changed=0` run;
3. `lab.yml` convergence and an immediate `changed=0` run;
4. host-side Looking Glass, kvmfr and the reviewed VFIO boot entry;
5. an empty private workshop location outside `/var/lib/libvirt/images`.

The source qcow2, Windows ISO, virtio ISO, evidence JSON and signed guest
installers remain private and never enter Git.

## Why virt-manager appears here

Windows installation, driver setup, signed Looking Glass host installation and
the virtual display are interactive guest operations. A SPICE recovery console
must exist before Looking Glass can carry real frames. `virt-manager` provides
that temporary console and device editor.

After `image-prepare.yml` seals the workshop qcow2, final domains are created by
`vm-create.yml`. Never edit a domain carrying HyperLab metadata in virt-manager;
use the lifecycle playbooks so its receipt, overlay, TPM, NVRAM and trust state
remain one transaction.

## Temporary workshop domain

Create one unmanaged domain with a name beginning `workshop-`. Keep its qcow2
outside the managed image store. Use:

- Q35 and UEFI;
- TPM 2.0 and Secure Boot for Windows 11;
- Windows 11 ISO plus the reviewed virtio-win ISO;
- SPICE as the recovery display and input path;
- the reviewed workload network (`clean` or `dirty`);
- the dGPU functions and the same 64 MiB ivshmem/kvmfr contract used by the
  final spec;
- memory that fits the physical host budget.

Do not add HyperLab metadata to the workshop domain. It is disposable and is
removed after the source qcow2 has been sealed.

## `win11clean`: personal singleton

Build this image from its own clean Windows installation. It is not generalized
and may contain the one intended personal Microsoft account.

Inside the guest:

1. complete Windows Setup and all required reboots;
2. install virtio storage/network/input and QEMU Guest Agent;
3. install the NVIDIA driver and verify the passed GPU has no device error;
4. install the exact Looking Glass host build required by the manifest;
5. install the virtual display, set it to 1920×1080 and retain SPICE as recovery;
6. verify the guest log reaches `Capture Start` through `D12`;
7. verify no Windows Update or file-rename reboot is pending;
8. collect evidence while Windows reports `IMAGE_STATE_COMPLETE`:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\windows\collect-hyperlab-evidence.ps1 `
  -Image win11clean `
  -IdentityMode personal-singleton `
  -LookingGlassBuild B7-263-g0140a3f6fb `
  -LookingGlassLog 'C:\ProgramData\Looking Glass (host)\looking-glass-host.txt' `
  -OutputPath 'C:\HyperLab\win11clean-evidence.json' `
  -MicrosoftAccountPresent `
  -NoCredentialReuse
```

Copy the evidence JSON out through private removable media or the temporary
recovery channel, then shut Windows down normally. Do not run Sysprep on this
singleton.

## `win11dirty`: generalized local template

Build this from a second clean installation. Do not clone `win11clean`: personal
identity and credentials must never cross into the dirty template.

Complete the same driver and Looking Glass checks using a dedicated local lab
account and no Microsoft account. After the final update reboot:

```powershell
cd $env:WINDIR\System32\Sysprep
.\Sysprep.exe /generalize /oobe /quit
```

Wait for Sysprep to finish successfully. Do not reboot. Collect the final
evidence immediately:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\windows\collect-hyperlab-evidence.ps1 `
  -Image win11dirty `
  -IdentityMode generalized-local-template `
  -LookingGlassBuild B7-263-g0140a3f6fb `
  -LookingGlassLog 'C:\ProgramData\Looking Glass (host)\looking-glass-host.txt' `
  -OutputPath 'C:\HyperLab\win11dirty-evidence.json' `
  -Generalized `
  -LocalLabAccountPresent `
  -NoCredentialReuse
```

The collector refuses unless the documented Windows Setup state is
`IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE`. This binds the receipt to completed
`/generalize`, instead of trusting only an operator switch or an undocumented
registry number.

Copy the evidence file out and shut down without another boot:

```powershell
shutdown.exe /s /t 0
```

A boot after generalization consumes the resealed state and invalidates the
source. Rebuild or generalize it again before capture.

## Validate and seal on the Arch host

Hash the private source independently:

```bash
sha256sum /private/workshop/win11clean.qcow2
sha256sum /private/workshop/win11dirty.qcow2
```

Validate the workshop receipt first:

```bash
ansible-playbook -K playbooks/windows-workshop.yml --check --diff \
  -e windows_workshop_policy=windows-workshops/win11clean.yml \
  -e windows_workshop_evidence=/private/workshop/win11clean-evidence.json \
  -e windows_workshop_manifest=images/win11clean.yml \
  -e windows_workshop_local_source=/private/workshop/win11clean.qcow2 \
  -e windows_workshop_source_sha256=<source-sha256>
```

Repeat without `--check`, then import the exact same file and checksum:

```bash
ansible-playbook -K playbooks/image-prepare.yml --check --diff \
  -e image_factory_manifest=images/win11clean.yml \
  -e image_factory_local_source=/private/workshop/win11clean.qcow2 \
  -e image_factory_source_sha256=<source-sha256> \
  -e image_factory_looking_glass_observed_build=B7-263-g0140a3f6fb
```

Repeat the real apply and then `image-validate.yml`. Use the same sequence with
`win11dirty`. The factory prints the artifact hash and policy values that must
be committed to the manifest before the frozen release campaign.

Only after sealing create the managed VM:

```bash
ansible-playbook -K playbooks/vm-create.yml --check --diff \
  -e guest_spec=vm-specs/win11dirty-disposable.yml
ansible-playbook -K playbooks/vm-create.yml \
  -e guest_spec=vm-specs/win11dirty-disposable.yml
```

The permanent clean VM follows its own reviewed spec and host memory budget.
