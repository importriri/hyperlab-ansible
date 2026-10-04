# A sealed Debian image claimed a QEMU Guest Agent it did not carry

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the image guest agent contract.
The check still has to run on Nitro against the sealed `arch`,
`arch-dev-20261003`, `debian` and `fedora` images.

## Symptom

The first Machine from `server-debian`, `srv-deb-01`, was created, defined
and started on Nitro, and then `vm-create.yml` failed:

```text
TASK [guest : Wait for QEMU Guest Agent readiness]
"stderr": "error: Guest agent is not responding: QEMU guest agent is not connected"
```

The domain was running with a DHCP lease; nothing answered on the agent
channel for three minutes.

## Root cause

`images/debian.yml` is the unmodified upstream Debian 13 genericcloud image
(its `sha256` equals `source_sha256`) and declared
`supports.qemu_guest_agent: true`. Debian's own package manifest for that
build, `debian-13-genericcloud-amd64-20261001-2618.json`, lists `cloud-init`
and `openssh-server` but not `qemu-guest-agent`. The claim was written by
hand and nothing checked it: the image factory verifies digests, receipts
and qcow2 shape, never what is inside the image. The Arch server worked only
because the Arch cloud image does carry the agent.

The agent is not optional for a Machine: `vm-guest-inventory.yml` reads the
new Machine's SSH host key through it and pins it, so the first SSH
connection never trusts a key shown on the network. Without it the Machine
cannot be reached safely.

## Fix

- `tools/image_guest_agent.py` opens a qcow2 with libguestfs, read-only and
  without booting it, and reports whether the `qemu-ga` binary and the
  `qemu-guest-agent.service` unit are present.
- The image factory's validation, which also closes every new seal, reads
  the manifest's claim for a Linux image and refuses the image when it
  claims the agent and does not carry it. A missing libguestfs is a refusal,
  never a skip.
- `images/debian.yml` now claims no agent and is only the Workbench base.
  `images/debian-server.yml` (not built) is that base captured with the
  agent; `server-debian`, `debian-dev` and `svc-jellyfin` use it, and
  `server-debian` is a draft until it is sealed.

## Regression proof

`tests/image_guest_agent_contract.py` runs the real tool against a fake
guestfish that answers like an image with and without the agent, and
requires the read-only direct-backend invocation, the refusal for an image
without the agent or with a binary but no unit, the check's place in the
validation tasks, and the corrected Debian manifests and Template. The
creation plan and Create view contracts require a draft Template never to be
offered.
