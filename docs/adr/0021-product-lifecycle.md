# ADR 0021 - From Image Factory to Project: the product lifecycle

## Context

The product model grew across several records:
[`0010`](0010-image-provenance-transaction.md) sealed bases and provenance,
[`0015`](0015-golden-image-capture.md) the Workbench capture,
[`../c10-machine-factory-contract.md`](../c10-machine-factory-contract.md)
Templates and Machines, [`0017`](0017-shell-machine-creation.md) creation
from the shell, [`0018`](0018-disposable-discards-on-stop.md) disposable
Machines, and [`../guest-workspace-shell.md`](../guest-workspace-shell.md)
Desks and Projects. Roadmap milestone 0 asks for one canonical record that
names every object, who owns it and how one becomes the next.

## Decision

```text
upstream image or Workbench candidate
  -> Image Factory          verify, import, generalize, seal
  -> Golden Image           images/<id>.yml, sealed, digest-pinned
  -> Template               templates/<id>.yml, reviewed product policy
  -> Machine                $XDG_STATE_HOME/hyperlab/machines/<id>.yml
  -> projected VM spec      vm-specs/.generated/<id>.yml, derived
  -> libvirt domain         created by the guest transaction
  -> Desk -> Project        inside the guest, organisation only
```

| Object | Authority | Created by | Changes after creation |
| --- | --- | --- | --- |
| Golden Image | checked-in manifest and the root-owned store | Image Factory, or a Workbench seal | never; a new seal is a new digest |
| Template | checked-in, reviewed | a commit | by review; a Machine keeps the version it was made from |
| Machine | user-owned registry outside Git | `hyperlabctl machine create`, the Create view | only through reviewed operations |
| VM spec | derived from the Machine | `hyperlabctl machine project` | regenerated, refused if the image was resealed |
| domain | libvirt, under the guest transaction | `vm-create.yml` | lifecycle operations; validation refuses drift |
| Desk, Project | the guest account | the guest's Workspace Shell | freely; never a boundary |

- **Sealed means immutable.** A Golden Image is generalized (no accounts,
  keys, machine-id or host identity), scanned for leftovers when it comes
  from a Workbench capture, and pinned by digest. A Machine records that
  digest; projection refuses a VM spec whose image was sealed again since.
- **A Template is policy, not a machine.** It names one image and what
  Machines from it may be: lifecycles, device capability, network
  allowlist, GPU handoff profiles, resource profiles and presentation.
- **A Machine is intent.** The record says what was asked for. Running
  state, trust, provenance and GPU ownership are observed by the host,
  never stored in the record and never reported by the guest.
- **Fresh install, empty Machines.** A new host shows *No Machines yet*.
  Checked-in fixtures such as `arch-dev-vfio` and domains defined outside
  HyperLab are not product Machines; Diagnostics lists them.
- **Lifecycle.** Permanent Machines are independent copies of the sealed
  image; disposable Machines are transient overlays that discard every write
  when they stop. Reset and destroy are explicit, confirmed operations.
- **Desk and Project** organise work inside one Machine: a Desk is a group
  of workspaces, a Project a named slot with a folder and programs. They
  carry no trust and never cross Machines; isolation is the Machine.

## Consequences

- Every object has one owner, and nothing is adopted implicitly: a disk is
  not a Golden Image because it exists, and a domain is not a Machine
  because it runs.
- Changing a Template never rewrites an existing Machine; a Machine moves to
  a new image only by being created again.
- The records above stay authoritative for their own parts; this ADR is the
  map between them.
