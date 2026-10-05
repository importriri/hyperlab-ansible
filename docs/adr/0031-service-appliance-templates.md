# ADR 0031 - Creating a service appliance from a Template

Status: proposed. The operator chooses before a services Template becomes
ready; today `svc-jellyfin` is a draft and Jellyfin is deployed by
`playbooks/jellyfin.yml`.

## Context

A service appliance is more than a Machine. Jellyfin needs a fixed address
on the services network (a DHCP reservation with its MAC), the one port the
host forwards to it, its backup and restore policy and its entry in the
service registry; `service-specs/svc-jellyfin.yml` holds those, and
`playbooks/jellyfin.yml` changes the host (registry, exposure) and the
guest (the Jellyfin role) in one run. The Machine factory, by contrast,
creates a Machine with a name the operator chooses, projects its VM spec and
runs one guest profile playbook. A Template for a service has to say who
owns the host side.

## Options

**A. A services Template names its reviewed service spec (recommended).**
The Template points at one checked-in service spec; the Machine's name, MAC
and address come from it, so only one Machine per service spec can exist
(a singleton, refused a second time). Provisioning runs the guest profile
(the Jellyfin role) like any Machine, then the existing service playbooks
register the service and install its exposure, each through the operation
runner with its own password prompt. The shell shows it among the Machines
on the services network.

**B. Services stay outside the Create view.** The Template is catalogue
documentation only; the appliance is deployed with its playbook from the
terminal, and appears in Machines only as an observed domain in
Diagnostics.

**C. The factory writes the service spec.** Rejected: an exposure and a
fixed address are host policy, reviewed in the repository, never generated
from a form.

## Recommendation

A. It keeps host policy reviewed in `service-specs/`, reuses the service
playbooks as they are, and gives the appliance the same lifecycle, backups
and shell presence as every other Machine.
