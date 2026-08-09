# hyperlabctl

`hyperlabctl` is the local control surface for HyperLab. It reads checked-in
policy plus live libvirt/host state and renders the same document for the CLI,
terminal panel, Waybar and action palette.

It owns no separate policy. A renderer cannot invent an action that the checked-in
registry does not expose.

## Useful commands

| Command | Purpose |
| --- | --- |
| `hyperlabctl status` | complete read-only host document |
| `hyperlabctl panel` | terminal cockpit over that document |
| `hyperlabctl doctor` | contract problems with concrete remedies |
| `hyperlabctl vm list` | managed/unmanaged domain state |
| `hyperlabctl net list` | five trust-domain networks |
| `hyperlabctl image list` | image manifests and sealed-base state |
| `hyperlabctl trust` | current GPU trust owner and allowed transitions |
| `hyperlabctl logs --level warn` | warning-or-higher HyperLab events |
| `hyperlabctl schema` | discovered status providers and fields |
| `hyperlabctl actions --all` | available and currently blocked reviewed actions |
| `hyperlabctl completion` | shell-completion candidates |

`preflight.yml` must have selected a hardware profile before hardware-dependent
sections can be complete.

## Read boundary

Status collection is unprivileged. Missing data degrades the affected section and
adds a problem record instead of blanking the whole cockpit. A provider reports
`Unavailable` for a missing source and `ContractError` when repository/live state
cannot both be true.

`runner.py` is the only process boundary used by providers. It fixes the locale
for machine-parsed output and gives callers explicit timeouts.

## Action boundary

Direct start/stop is limited to unmanaged libvirt domains. A domain carrying
HyperLab metadata must go through its checked-in VM spec and lifecycle playbook.
That preserves image validation, memory checks, locks, receipts, GPU ownership and
destructive confirmations.

Privileged actions therefore resolve to a quoted command for operator review; the
Waybar/palette surface does not run them silently.

Targets come from real non-symlinked files under the allowed manifest/spec roots.
An action whose required playbook is missing from the checkout is not offered.

Examples:

```bash
hyperlabctl actions --choices spec
hyperlabctl actions --resolve vm.managed-start --spec vm-specs/debian-dev.yml
```

## Status providers

A provider is one `Provider` subclass under `hyperlabctl/providers/`. Its `key`
becomes a status-document section. Keep collection and problem detection in the
provider; add the matching operator remedy in `remedies.py` in the same change.

Local read-only extensions can live under
`~/.config/hyperlabctl/providers/`. A broken local provider is recorded and
skipped rather than taking down the rest of the document.

## Commands, views and actions

- commands: `hyperlabctl/commands/<name>.py` with a `Command` subclass;
- panel views: the view registry in `panel/views.py`;
- actions: the central action registry.

The action registry is the only place the panel, keybinds and palette learn which
operations exist. That keeps UI code out of lifecycle policy.

## Configuration

Precedence is package defaults, `/etc/hyperlabctl/config.yml`, user config, then
flags. Unknown config keys are refused instead of creating silent settings.

The host role installs `/usr/local/bin/hyperlabctl` as a wrapper around the local
checkout. Repository code is not copied into `/usr/local`.

## Waybar

`hyperlabctl waybar --field {trust,ram,gpu,vms}` renders the compact status fields.
`hyperlabctl watch` follows libvirt events for the collapsed status path. The
slow-polling drawer fields also accept the managed real-time signal after a state
change so UI refresh does not require aggressive polling.

## Verification

Run the isolated component suite and the repository integration contract:

```bash
PYTHONDONTWRITEBYTECODE=1 python tools/hyperlabctl/tests/run.py
python tests/hyperlabctl_contract.py
```

The repository verifier discovers the integration contract automatically. Keep
fixed test counts out of this document; the suite itself is the source of truth.
