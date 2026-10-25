# C10 — Machine Factory and Workspace Experience

C10 turns the current hardware-development workloads into a product lifecycle.
`arch-dev-vfio` remains a Nitro reference fixture; it is not the Golden Image.

## Product model

```text
Upstream source / ISO
  -> Image Factory
  -> sealed Golden Image
  -> Template / Preset
  -> user-created Machine
  -> Workspace / Desk
  -> Project
```

Golden Images, Templates and Machines are distinct objects in schemas, storage
and UI.

A Golden Image is immutable and generalized. It may contain the OS, reviewed
HyperLab guest integration, generic workstation packages, safe drivers and the
workspace shell. It must not contain user secrets, SSH keys, final hostnames,
machine-specific identity, runtime trust claims, GPU ownership state or normal
writable workload state. A reference VM proves a recipe; it is not itself the
Golden Image. Golden Images never appear in `Machines`.

A Template is a product recipe over a compatible Golden Image. It declares
supported lifecycles, device capabilities, resource profiles, network profiles,
workload bundles, presentation defaults and required guest integration.
Templates never appear as running Machines.

A Machine is a user-created runtime instance. A clean installation starts with:

```text
Machines

No machines yet.

[ Create Machine ]
```

Product-created machine state must move out of `vm-specs/.generated` into a
user-owned host-side persistent registry outside the Git checkout. Checked-in VM specs
remain development and hardware fixtures.

## Architecture review decisions

C10 freezes these product boundaries before implementation.

### Template catalogue is checked-in product policy

Templates are reviewed repository content, separate from Golden Image
manifests, development fixtures and runtime Machine state.

~~~text
images/       Golden Image manifests and provenance
templates/    product Templates / Presets
vm-specs/     checked-in development and hardware fixtures
runtime       user-created Machine records outside Git
~~~

A Template has a stable identifier and schema version.

A materialized Machine records the exact Template identity/version and Golden
Image digest from which it was created. Changing a Template later does not
silently rewrite an existing Machine.

### Machine intent and observed runtime are separate

The Machine Factory owns declarative Machine intent.

Libvirt and the existing host providers remain authoritative for observed
runtime state.

A Machine record may declare lifecycle, resources, network profile, requested
device/GPU capability and requested presentation capabilities.

The runtime registry must not claim running state, trust, provenance, GPU
ownership or transport availability.

Materialization reuses the existing planners, locks, confirmations and libvirt
transactions instead of creating a second VM engine.

The resources a record receives come from one factory function. The creation
plan reports what each profile resolves to and the custom limits through the
same code (`custom_limits`), and the factory holds every custom request to
those limits itself: memory at least the image's `min_memory_mb`, disk at
least the sealed image, vCPUs within the factory's ceiling (the plan narrows
it to the host's).

`machine create --project` records and projects a Machine as one staged
step under the registry lock: it checks the name is free, writes the
generated spec, and publishes the record last. The creation is not done
until the stored record has been synced, read back and found to have the
digest it was published with. The publication names its file (inode and
digest) before `os.link` puts it in place, so a failure at any later step,
a handled cancellation (`KeyboardInterrupt`) included, undoes it under the
same lock: the record this creation
published goes first, and only while it is the same file (inode) with the
same bytes; then, once that removal is synced, the spec, again only while
it is the file this creation wrote with its bytes. A refusal therefore
leaves neither record nor spec; the shell bridge creates Machines only
this way, so a refused creation leaves no record behind
([ADR 0017](adr/0017-shell-machine-creation.md)). Plain `machine create`
and the library's `create_machine()` (used by `create_from_template()`)
publish and undo their record the same way, holding the registry lock
across both. When the undo cannot finish (a removal
fails, a file was replaced, the removal cannot be synced), the refusal says
"cleanup incomplete" and names what stays: bytes this creation did not
write are never removed, and the spec stays whenever the record's
withdrawal did not complete, so a record is never left without its spec by
the undo.

The undo is not atomic, and nothing here holds across process death or
power loss. A creation killed before its record is published leaves a
spec without a record: the next request for that name is refused with
"already exists" until `hyperlabctl compose delete NAME --confirm NAME`
removes the spec. One killed after the publication leaves both, as a
completed creation would, with no provisioning started. The generated
spec's directory is not synced, so after a power loss a published record
may come back without its spec.

A record can be withdrawn, and only by its digest. `machine create` reports
the SHA-256 of the record it stored; `machine withdraw ID --record-sha256
DIGEST` removes that record only while its bytes still have that digest, no
generated spec equal to its projection exists, and the libvirt domain list,
read every time, has no domain with its name. An unreadable domain list is
a refusal, and so is a generated spec that cannot be read as exactly one
YAML mapping: a link, anything but a regular file, an unreadable or
non-UTF-8 file, malformed YAML, several documents or a repeated key. Only
a spec that parsed is compared with the projection; a parsed spec that
differs is stale and stays. The digest names a record; it is not an
authorization, since anyone who can read the record can compute it. `create`, `project` and
`withdraw` hold the registry lock (`.lock` in the registry directory), so a
record is never withdrawn while its spec is being written; a lock held for
more than five seconds is a refusal. `withdraw` is for the manual path, where
`create` and `project` are two commands and the second can refuse
([ADR 0053](adr/0053-withdraw-machine-intent.md)).

### Managed, fixture and external domains are different populations

Normal `Machines` presents only product-managed user-created Machines.

Checked-in campaign domains such as `arch-dev-vfio` remain fixtures during C10
and do not define first-boot product inventory.

A libvirt domain absent from the product Machine registry is not silently
hidden. Diagnostics / Inventory may expose it as a fixture or unmanaged domain
with observed facts, without granting product lifecycle semantics that were
never registered.

### Workspace presentation is template-owned appearance, not trust

Templates may select a reviewed workspace appearance profile such as
`development-blue`.

The Development Workstation may use the established blue geometric HyperLab
art family. This remains presentation only.

The guest workspace never establishes trust and never changes host-owned trust,
provenance, wallpaper or RGB state. The host provenance border remains
authoritative.

The guest workspace shell lives in a dedicated role/module rather than growing
product presentation inside `guest_desktop_hyprland`.

The compositor role owns mechanics. The workspace-shell role owns presentation.

## Reference fixture and capabilities

`arch-dev-vfio` remains the Nitro reference fixture during C10. It proves Linux
VFIO, NVIDIA, headless Hyprland, Looking Glass, input, audio, resources, reboot,
recovery and the future workstation recipe. C10 does not freeze its current rice.

`VFIO` is not a workstation identity. `standard` and `vfio` are device
capabilities that may be offered by the same Development Workstation Template.

Network profile and GPU capability are independent. The current rule excluding
`services` from VFIO is superseded by C10. A future service Machine may request GPU when its Template, Golden Image,
detected hardware and host-owned GPU policy permit it. C10 does not invent a trust rank for `services`.

A `gpu_handoff_profile` may lower, never raise, the contamination class that a
ranked network identity already implies: a `dirty` Machine may hand off as
`dirty` or `lab`, never as `dev` or `clean`. The Machine factory, `guest_plan.py`
and the root-owned `tools/gpu_handoff_policy.py` each enforce this, so the
privileged tool holds the rule even for a plan that did not come from the
factory. Removal is exempt so a stale policy can always be cleaned up.

The `managed-machine` tag on a projected VM-spec is a provenance claim, not a
security boundary. Anyone who can write `vm-specs/` and run the guest lifecycle
with sudo can write that tag. What the privileged path enforces regardless of
provenance is the ceiling above, the reviewed trust levels, the exact
`device_profile=vfio` request and the fail-closed policy-directory checks. The
Template allowlist for a `services` Machine is enforced by the factory and by
review of the checked-in Template; the root tool does not re-derive it.

The ladder, the policy surfaces and the field vocabulary are recorded in
[`gpu-handoff-policy.md`](gpu-handoff-policy.md).

Looking Glass is an explicit cross-OS presentation capability, not a consequence
of Windows. Runtime transport availability remains backend-authoritative.

## Workspace experience

The current guest rice is transitional. The target is a recognizable HyperLab
workstation, not generic Hyprland with a HyperLab wallpaper.

`guest_desktop_hyprland` keeps compositor mechanics, display/session setup,
portals, input namespace, lock primitives and NVIDIA/headless-output mechanics.

A separate Quickshell Workspace Shell owns presentation: quiet top surface,
workspace indicators, launcher, local audio/network/session state, OSD,
workstation identity, typography, spacing, icons and motion.

Waybar is transitional and leaves the preferred path only after physical
acceptance. Rofi and Mako may remain recovery/transitional components.

The workspace shell never owns HyperLab trust, provenance, GPU ownership, host
inventory, host network policy or host lifecycle. Wallpaper and theme never
establish trust.

The accepted input namespace remains:

```text
SUPER       host HyperLab navigation
ALT         workspace navigation
RIGHTCTRL   Looking Glass transport escape
```

The initial Development Workstation uses the established blue geometric DEV
visual direction. Host-owned DEV provenance borders and host-owned RGB remain
the security-relevant presentation.

## First vertical slice

```text
Fresh HyperLab
  -> Machines: empty
  -> Create Machine
  -> Development Workstation Template
  -> Permanent
  -> Standard or Dedicated GPU / VFIO
  -> materialize runtime Machine
  -> Start
  -> reviewed login/recovery handoff
  -> HyperLab Development Workspace
  -> Looking Glass when supported
```

No fake inventory, fake progress or fabricated runtime state.

## Implementation order

1. Add a real Template layer between Golden Images and Machines.
2. Move product-created machine state out of Git.
3. Separate network profile from GPU capability.
4. Make Looking Glass an explicit cross-OS capability.
5. Define the generalized Arch Workstation image recipe.
6. Establish the Quickshell Workspace Shell and replace Waybar after acceptance.
7. Implement empty first-boot Machines and Template-driven Create Machine.
8. Create Standard and VFIO Development Workstations from the same model.
9. Revalidate Nitro, reboot, recovery and idempotence.
10. Capture the filmable acceptance sequence.

C10 does not retroactively rewrite C9.
