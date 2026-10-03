# Fixture domains vanished from the shell once Machines became product-only

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Quickshell runtime contract.
Physical acceptance on Nitro is pending.

## Symptom

C10 switched the Machines workspace to the registry-backed product inventory.
On a development host with an empty Machine registry, the workspace correctly
became empty, and its empty state told the operator that fixture and external
libvirt domains "stay in Diagnostics".

Diagnostics did not list them. Its inventory section only counted the rows of
the same product inventory, so `arch-dev`, `arch-dev-vfio` and
`arch-minimal-ssh` disappeared from the shell while they were still running.

## Root cause

The product inventory deliberately does not query libvirt when the registry is
empty: first install is a valid, empty inventory and must not depend on
runtime discovery. That left no source in the shell for unregistered domains,
and the empty-state copy promised a view that did not exist.

## Fix

Diagnostics now has its own read-only observation channel:

```text
privatestack-hyperlab diagnostics-domains
  -> hyperlabctl waybar --field vms
  -> ShellState.observedDomains
  -> ShellState.outsideDomains (names with no product Machine row)
  -> Diagnostics > Inventory > Outside the product inventory
```

Each row shows the domain name, its observed state and whether it is a HyperLab
fixture, an external domain or unreadable. The rows carry no actions and never
join `ShellState.machines`, so a libvirt domain still cannot become a product
Machine because it exists.

The product Machine states that have no libvirt counterpart now read as
"Not created", "Configuration drift" and "Runtime unavailable".

## Regression proof

- `tests/host_quickshell_runtime_contract.py` (truth scenario): a domain that
  matches a product Machine is not listed twice, fixture and external domains
  are classified, nothing observed joins the product inventory, and a malformed
  observation clears stale rows. Removing the product filter fails the scenario.
- `tests/c10_machine_cli_product_inventory_contract.py`: the bridge keeps raw
  domains and product Machines on separate sources.
