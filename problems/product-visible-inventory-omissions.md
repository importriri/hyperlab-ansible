# Deferred visible labels were missing from the migration inventory

Status: corrected in the proposed migration boundary and its contract.
The listed surfaces still need migration; hardware acceptance remains open.

## Symptom

The release plan recorded several remaining old product labels, but omitted
host and guest lock labels, guest Ly text, shell-action failure messages,
provisioning diagnostics, Gaming Mode help and a session shutdown refusal.
An operator could encounter the previous name outside the recorded list.

## Root cause

The existing check required a closed list of files in the roadmap and ADR.
It inspected machine-bridge refusal literals, desktop entry names and the
fallback bar, but omitted other visible paths. In particular, shell-action
stderr is recorded in native Diagnostics operation details and also reaches
failure-OSD state. The OSD displays `Failed` rather than the full reason.
Passing the closed list did not establish a complete inventory of the tree.

## Fix

Extend ADR 0058 and the open release item with the known missing files.
Describe the inventory as known at `233b046`, without claiming exhaustiveness.
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
