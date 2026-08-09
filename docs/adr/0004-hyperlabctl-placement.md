# ADR 0004 - Where hyperlabctl lives, and what it may depend on

## Context

The CLI has to orchestrate playbooks and `virsh` without becoming a
second implementation of either. It also has to run on the host the iron
principle describes: TTY-only, no GUI, only the packages the lab bundle
installs.

## Decision

`hyperlab-ansible/tools/hyperlabctl/`, next to the automation it
drives, packaged so it can be installed but usable straight from the
checkout.

The core depends on the Python standard library plus PyYAML, which is
already a dependency of Ansible itself. No Typer, no Rich, no Pydantic,
no `libvirt-python` in the core path: `virsh` is already there and is the
interface libvirt documents.

Anything richer - colour, TUI, tables - is an optional extra that the
core never imports. `--json` and `--no-color` are core, not extras.

## Consequences

- The CLI works on a freshly bootstrapped host with zero extra installs.
- The CLI holds validation, locking and orchestration; the roles hold
  provisioning. A behaviour that exists in both is a bug in one of them.
- Shell completion and a man page are additive and do not change the
  dependency floor.
