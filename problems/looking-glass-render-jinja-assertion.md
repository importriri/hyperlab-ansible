# Looking Glass render gate embeds a template inside a Jinja constant string

Author: [importriri](https://github.com/importriri).

Status: open verifier defect.

## Symptom

`tests/render.yml` reaches the Looking Glass invariant block and fails even
though the surrounding cockpit and transport rendering tasks are green.

Ansible also warns that Jinja constant strings should not contain embedded
templates. The failing assertion searches for this literal form:

```text
input_patch_sha256: {{ looking_glass_input_patch_sha256 }}
```

The assertion evaluates false and stops the render suite.

## What is wrong

The verifier mixes two evaluation layers. A Jinja expression is itself written
inside a quoted Jinja constant string, so the assertion depends on template
syntax being reinterpreted inside text.

That is both fragile today and explicitly warned against by current
`ansible-core`. A test for source provenance must compare a resolved value or
inspect the source text without asking Jinja to evaluate a template embedded
inside another expression.

## Required fix

Keep the source-provenance invariant, but construct the expected text from
normal expression operands or compare the parsed/rendered value directly.

Do not weaken the gate to a substring that can pass with an unrelated checksum.
The test still needs to prove that the Looking Glass input patch identity comes
from the reviewed variable.

## Closure gate

This problem stays open until all of the following are green on the candidate:

```bash
ansible-playbook -K tests/render.yml
./verify.sh
```

The warning about an embedded template must disappear with the assertion
failure. Until then, documentation and hardware successes must not be described
as a fully green repository verifier.
