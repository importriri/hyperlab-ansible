# The guest runtime fixture lost user-installed Ansible

## Finding

The structural-contract job failed at `a424a4a269` with
`FileNotFoundError: 'ansible-playbook'`. CI had already installed Ansible
with `pip install --user`. The shared invocation helper in
`tests/guest_contract.py` replaced PATH with system directories, then
launched the bare executable name. Ansible in the caller's user bin
directory was no longer discoverable. A system installation hid this
defect locally; the inventory contract uses the same helper.

The private HOME created a second failure: Python derives its user package
directory from HOME, so finding the launcher alone would still leave its
user-installed modules unavailable.

## Fix and evidence

Resolve the required Ansible executable from the caller's PATH before
building the child environment, then invoke that absolute path. Refuse a
missing executable rather than falling back to a different installation.
Pass the caller's Python user base explicitly through `PYTHONUSERBASE`.
Keep the fixed child PATH, private HOME, repository Ansible configuration
and private Ansible directories; inherit no other caller settings.

`python tests/guest_runtime_environment_contract.py` exercises the actual
helper with a recording launcher outside the system PATH and a dependency
available only in a temporary Python user site. It checks the executable,
real argv, package import and isolated environment, then removes the
launcher and requires a deliberate refusal. Restoring the bare name or
removing the user base turns this regression red even on a machine that
has system Ansible. The existing guest and inventory contracts still
exercise real Ansible, stubbed libvirt and strict SSH over a pipe.

This is software verification of the fixture and its callers. A hosted
workflow rerun remains separate evidence; no hardware behavior changes.
