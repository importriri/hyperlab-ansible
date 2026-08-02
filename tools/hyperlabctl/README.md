# hyperlabctl

The control surface for the Hyperlab. It reads the repository contract and
libvirt, renders one document three ways, and owns no policy of its own.

Per ADR 0004: standard library plus PyYAML, `virsh` rather than
`libvirt-python`, `--json` and `--no-color` in the core rather than an extra.
Per ADR 0014: the bar, the palette and the panel are renderers of that one
document, and privilege is a field rather than a convention.

## Running it

No install step is required. From a checkout, each public command has one
operator-facing purpose:

| Command | Purpose |
|---|---|
| `tools/hyperlabctl/bin/hyperlabctl status` | Render the complete read-only host document. |
| `tools/hyperlabctl/bin/hyperlabctl panel` | Open the terminal cockpit over the same document. |
| `tools/hyperlabctl/bin/hyperlabctl doctor` | Report contract problems with concrete remedies. |
| `tools/hyperlabctl/bin/hyperlabctl vm list` | List domains and their managed/unmanaged identity. |
| `tools/hyperlabctl/bin/hyperlabctl net list` | List the five network domains and live state. |
| `tools/hyperlabctl/bin/hyperlabctl image list` | List image manifests and sealed-base state. |
| `tools/hyperlabctl/bin/hyperlabctl trust` | Show current GPU trust ownership and permitted transitions. |
| `tools/hyperlabctl/bin/hyperlabctl logs --level warn` | Show warning-or-higher Hyperlab journal events. |
| `tools/hyperlabctl/bin/hyperlabctl schema` | Describe every discovered status provider and field. |
| `tools/hyperlabctl/bin/hyperlabctl actions --all` | Show available and currently blocked reviewed actions. |
| `tools/hyperlabctl/bin/hyperlabctl completion` | Emit shell-completion candidates without changing the host. |

`preflight.yml` must have run once. Without
`/etc/privatestack/hardware-profile.yml` there is no selected profile, so the
memory and gpu sections degrade to null and say why.

Exit codes: `0` fine, `2` at least one problem of severity `error`, or a
refused action.

## The panel

Four status tiles with gauges, tabbed views over domains, networks, images,
problems and the journal, a detail pane on wide terminals, and a footer that
greys out the actions the selected row cannot take.

    j k   move          tab 1..5   change view      / filter
    s x   start stop    i inspect  ? help  r refresh  q quit

Catppuccin Mocha exactly when the terminal can redefine colours, and the
nearest 256-colour approximations when it cannot. foot can.

It is split in two on purpose. `panel/model.py` turns a document into a screen
of plain data and holds every decision; `panel/ui.py` only paints it. The suite
asserts on the model and never drives a terminal, which is why the panel has
tests at all.

## Two paths, one boundary

Reads need no password. Direct `vm start` / `vm stop` are deliberately limited
to unmanaged libvirt domains. A domain carrying M3's Hyperlab metadata must go
through its checked-in VM spec and lifecycle playbook, so the cockpit cannot
skip state validation, sealed-base checks, locks or destructive confirmations.
Those managed actions are marked `privileged` and the palette prepares their
`ansible-playbook -K` command without executing it.

A permitted direct start still fails closed when the memory budget is
unavailable, when the requested allocation does not fit, or when a VFIO domain
is absent from `gpu_domain_profiles`. The refusal lives in `operations.py`, so
the panel and the CLI refuse the same way with the same numbers. The OOM killer
is not an error message.

## Actions appear as the queue is merged

Each action declares the playbook it `requires`. An action whose playbook is not
in this checkout is not offered, so the palette never lists something that
cannot exist at this revision. Targets are selected from real, non-symlinked
files below `vm-specs/` or `images/`; the registry resolves them to an argv list
and only then emits a shell-quoted command.

```bash
# Include actions whose required playbook is not present at this revision.
hyperlabctl actions --all

# Print the checked-in VM specs accepted by the action registry.
hyperlabctl actions --choices spec

# Resolve one managed start to a shell-quoted Ansible command; do not execute it.
hyperlabctl actions --resolve vm.managed-start --spec vm-specs/debian-dev.yml
```

Global flags such as `--json`, `--no-color` and `--repo` are accepted before or
after the subcommand, so both `hyperlabctl --json actions` and
`hyperlabctl actions --json` are equivalent.

## Adding a section to the status document

One file. Nothing central lists providers: the package imports every module it
contains and every `Provider` subclass registers itself.

    # hyperlabctl/providers/temperature.py
    from .base import Provider

    class TemperatureProvider(Provider):
        key = "temperature"          # the section name in the document
        order = 80
        summary = "package temperature"

        def collect(self, ctx):
            return {"celsius": int(ctx.read_text("/sys/.../temp1_input")) // 1000}

        def problems(self, ctx, section):
            if section["celsius"] > 90:
                return [{"id": "temperature.throttling", "severity": "warn",
                         "message": "package at %d C" % section["celsius"]}]
            return []

Raise `Unavailable` when a source is missing and `ContractError` when the
repository says something impossible. Either way the section becomes null, the
reason lands in `problems`, and every other section still renders. A provider
that crashes outright is caught too: a cockpit that blanks because one read
failed is worse than no cockpit.

Add the problem's remedy to `remedies.py` in the same commit - a test scans the
provider sources and fails if any declared id has no fix.

## Adding it without touching the package

Drop the same file in `~/.config/hyperlabctl/providers/`. It becomes a section
of the document, a row in `schema`, and a line in the panel, with nothing else
changed. A file that raises on import is recorded and skipped rather than
fatal.

## Adding a subcommand, a view, an action

Same rule for all three. `hyperlabctl/commands/<name>.py` with a `Command`
subclass. `panel/views.py` with a `View` subclass, which becomes a tab and is
counted in the tab bar. `registry.py` for an action, which the palette, the
keybinds and the panel all read - and which is the only place any of them may
learn what the CLI can do.

## Configuration

Package defaults, then `/etc/hyperlabctl/config.yml`, then
`~/.config/hyperlabctl/config.yml`, then flags. Only keys that already exist in
`DEFAULTS` are honoured, so a typo in a config file cannot invent a setting.

## Talking to a process

`runner.py` is the only module that starts one. It forces `LC_ALL=C` and
`LANG=C` for machine-parsed output, preserves an explicit no-timeout request,
and gives each caller a real timeout rather than relying on shell wrappers.
That is what makes every provider testable offline: the suite swaps in
`RecordedRunner` and replays captured output, with no mocking library and no
host.

## The bar

`hyperlabctl waybar --field {trust,ram,gpu,vms}` prints one pill; every field
returns the same four keys, so one set of CSS rules covers the whole drawer.

`hyperlabctl watch` blocks on `virsh event` and prints when something actually
happens - that is what the collapsed pill runs. Its process timeout is longer
than the requested heartbeat, and only the documented no-event result loops;
real libvirt errors stop the stream instead of spinning forever. The drawer
pills poll slowly and take `SIGRTMIN+8`, which the CLI raises after anything
that moves an unmanaged domain. The signal number is asserted on both sides by
`tests/hyperlabctl_contract.py`, because drift there is invisible at runtime.

## Tests

```bash
# Run the isolated CLI suite without reading or writing bytecode caches.
PYTHONDONTWRITEBYTECODE=1 python tools/hyperlabctl/tests/run.py

# Run the repository integration contract; it also executes the isolated suite.
python tests/hyperlabctl_contract.py
```

524 checks, no pytest, exit 1 on any failure. `tests/world.py` builds a whole
fake host in a temp directory: repository, group_vars, sysfs PCI tree, meminfo,
the gpu-handoff state file, image manifests and recorded virsh output.

The contract test is discovered by `verify.sh` and by CI through
`tests/*_contract.py`, so the CLI is gated without an edit to the workflow -
which is the rule that file states about itself.

Lint with `ruff check tools/hyperlabctl`. `ruff.toml` records which rules are
on and why the rest are off.

[`MUTATIONS.md`](MUTATIONS.md) lists what was deliberately broken to confirm the suite notices,
including the five mutations that survived their first run and what each one
exposed. Replay them with `PYTHONDONTWRITEBYTECODE=1` and a timeout: a
same-length edit can be masked by a stale bytecode cache, and one mutation makes
the suite hang rather than fail.
