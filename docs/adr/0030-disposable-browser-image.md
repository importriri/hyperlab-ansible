# ADR 0030 - How the disposable browser image gets its session

Status: proposed. The operator chooses before the image is built; the draft
`browser-disposable` Template and the `arch-browser` placeholder are the
same whichever option is chosen.

## Context

`browser-disposable` is a Machine for throwaway browsing on the `dirty`
network ([ADR 0029](0029-template-review-gate.md) class `disposable`): no
GPU, no Looking Glass, a libvirt transient disk that discards everything at
each stop ([ADR 0018](0018-disposable-discards-on-stop.md)). Two facts shape
its image:

- **No rice after boot.** A workstation gets its rice from a profile
  playbook after the first boot. A disposable Machine would lose it at every
  stop, so the browser session must already be inside the sealed image.
- **No account in the image.** The Workbench generalization removes every
  ordinary account (UID 1000 to 59999) and its home; the account cloud-init
  creates at each boot has a name only the Machine knows. A session that
  starts by itself needs an account that is part of the image.

## Options

**A. Capture through the Workbench (recommended).** A VM spec `arch-browser`
(standard device, `dirty` network) is built by a reviewed profile playbook
`playbooks/guest-arch-browser.yml`, with one new role: a system account
`browser` below UID 1000 with its home under `/var/lib`, greetd starting
`cage` with Firefox as that account, no clipboard and no shared folders. It
is then adopted, sealed, imported and validated exactly as `arch-dev`
(ADR 0015), and the leftover scan already ignores system accounts. Nothing
new in the Workbench.

**B. Derive offline (ADR 0026, extended).** The Workbench derives
`arch-browser` from the sealed `arch` base with a package list and, new, a
reviewed set of files and units copied from the repository into the image.
Nothing boots, but the Workbench gains a way to write configuration into an
image, which is new surface to review.

**C. A workstation image as disposable.** Rejected: its session comes from a
profile playbook after the first boot and would be gone at every stop.

## Recommendation

A. It reuses the capture path that already sealed `arch-dev-20261003`, adds
one ordinary profile role instead of a new Workbench capability, and the
built domain can be tried before it is sealed. B can follow if more
appliance images need configuration without a candidate VM.

## Open with either option

- the browser (Firefox recommended; Chromium is the alternative);
- whether a download is ever allowed to leave the Machine: today nothing
  crosses back to the host, and the roadmap's data crossing (milestone 6)
  decides how a file could.
