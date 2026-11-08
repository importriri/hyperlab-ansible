# Deferred visible labels were missing from the migration inventory

Status: corrected in the proposed migration boundary and its contract.
The listed surfaces still need migration; hardware acceptance remains open.

## Symptom

The release plan recorded several remaining old product labels, but omitted
host and guest lock labels, guest Ly text, shell-action failure messages,
provisioning diagnostics, Gaming Mode help and a session shutdown refusal.
The host Ly gate, guest idle fallback and session template, keyboard failure,
root Gaming Mode help and guest NVIDIA readiness error were also missing.
An operator could encounter the previous name outside the recorded list.

## Root cause

The existing check required a closed list of files in the roadmap and ADR.
It inspected machine-bridge refusal literals, desktop entry names and the
fallback bar, but omitted other visible paths. In particular, shell-action
stderr is recorded in native Diagnostics operation details and also reaches
failure-OSD state. The OSD displays `Failed` rather than the full reason.
Passing the closed list did not establish a complete inventory of the tree.
The QML scan covered only the host directory, and the desktop list had no
coverage check against repository sources, so the guest surfaces escaped it.

## Fix

Extend ADR 0058 and the open release item with the known missing files.
Describe the inventory as known at `db7c99b`, without claiming exhaustiveness.
Keep host and guest lock/login surfaces deferred with their deployment
readers, rather than changing their runtime input during documentation work.
The physical presentation gate remains open.

## Regression proof

`tests/product_display_name_contract.py` requires every known file in both
the ADR and the open roadmap item. An AST scan checks shell-action stderr
prefixes, parsed host hyprlock label blocks pin the wordmark and subtitle,
and guest lock-function literals and parsed Ly task data pin the guest labels.
Removing either the lock template or shell-action bridge from the open item,
adding an unlisted stderr prefix, or changing the pinned lock/login data
fails the deferred-surface check.
Host Ly defaults are parsed to pin both gate values; every desktop source
must be inventoried with its parsed Name and Comment, including the guest
template. The QML scanner covers both host and guest recursively and permits
exactly one existing guest desktop fallback. Additional old-name QML, changed
host gate values, guest session drift and unlisted desktop files fail.
Shell printf formats and the root helper's argparse AST pin the newly
inventoried stderr/help messages, with exact documentation in both records.
