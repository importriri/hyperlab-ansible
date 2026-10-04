# polkit asked for root's password in Machines made from a Template

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest and workstation guest
contracts. The physical recheck on a new Machine is pending; `dev-01` was
unblocked by hand before the fix.

## Symptom

On `dev-01`, installing from Flathub and other polkit actions asked for the
password of `root`. Root has no password, by design, so the action could
not be authorised at all.

## Root cause

cloud-init created `sid` with a sudoers rule and nothing else: no
supplementary group. polkit does not read sudoers. Its default rules treat
one group as administrators: `wheel` on Arch and Fedora, `sudo` on Debian
and Debian-based images such as Parrot. With no administrator in that group,
polkit falls back to `root` for `auth_admin`.

The manual fix on Nitro was `usermod -aG wheel sid` on `dev-01`.

## Fix

- `guest_admin_groups` in `group_vars/all/guest.yml` maps an image's
  `os_variant`, without its release number, to the administrator group of
  its distribution.
- The `guest` role resolves that group when it creates a new Machine and
  writes it in the user data, so cloud-init puts the account in it on first
  boot. A variant that has no entry refuses before any seed is written.
- `workstation_access` adds the account to `wheel`, appending, so a
  workstation seeded before this fix converges on its next profile pass.

Root still has no password: the account authenticates polkit actions with
its own password, the one the workstation profile sets.

## Not changed: passwordless sudo

cloud-init also gives the account `NOPASSWD` sudo. The profile playbooks
need it: they reach the guest over SSH with the key and become root without
a password. Removing it after the first provisioning means every later
profile pass must ask for the guest account's password, and the Machine's
sudo becomes as strong as that password instead of the SSH key. That is a
hypervisor-hardening decision, recorded in roadmap milestone 10, not a
side effect of this fix.

## Regression proof

`tests/guest_contract.py` renders the user data and requires the account in
the given group, with root disabled and no password; requires the group to
be resolved and checked before the seed is rendered, only for a new
transaction and outside validation and state; and requires every Linux image
manifest to have an administrator group. `tests/workstation_guest_contract.py`
requires the appending `wheel` membership in `workstation_access`.
