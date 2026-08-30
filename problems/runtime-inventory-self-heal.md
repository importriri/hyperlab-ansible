# Ephemeral guest inventory could disappear before an on-demand action

Author: [importriri](https://github.com/importriri).

Status: open integration gate.

## Symptom

Guest SSH and Linux Looking Glass actions consume a runtime inventory below
`$XDG_RUNTIME_DIR`. That file is intentionally ephemeral.

After a reboot, cleanup or a fresh runtime session, an otherwise healthy
managed guest could therefore be running while the controller had no safe
runtime inventory file to resolve its address.

## Failed approaches

The first self-heal attempt changed the inventory playbook privilege contract
and immediately collided with the existing guest-inventory test.

A later attempt made the desktop action invoke Ansible directly. The component
suite rejected that route because `vm.inventory` is part of the authoritative
CLI contract, not a special UI-only playbook escape hatch.

Both failed attempts were transactional and restored their source changes.

## Candidate boundary

The reviewed direction is:

```text
open action
  -> hyperlabctl vm inventory <checked spec>
  -> authoritative inventory playbook
  -> strict runtime file validation
  -> guest SSH / Looking Glass action
```

The runtime directory and inventory must be real paths owned by the current
operator. The inventory must be a regular non-symlink file with mode `0600`.

An existing unsafe file is a refusal, not something self-heal silently replaces.
Only a genuinely missing inventory is eligible for authoritative regeneration.

## Why the gate remains open

The route has gone through multiple contract revisions and the repository still
has an unrelated open Looking Glass render assertion. This problem is not
closed by the existence of recovery code alone.

Closure requires the final CLI route, guest-inventory contract, component suite,
mutation tests, lint, playbook syntax and complete repository verifier to pass
together, followed by a real missing-inventory recovery on the Nitro host.
