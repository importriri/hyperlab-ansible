# ADR 0048 - A key vault: private keys in a Machine without a network

Status: proposed.

## Context

Today an SSH key used from a Machine (to reach GitHub, to sign commits)
lives inside that Machine. Code that compromises the Machine takes the
key, and with it the operator's identity elsewhere, beyond the Machine's
own lifetime. Qubes OS answers this with split-SSH and split-GPG: the key
lives in a qube without a network, and every use crosses a policy the
operator confirms. HyperLab has no qrexec, but it has the same two parts it
needs: a host that decides, and a channel the host assigns (virtio-vsock,
whose context id libvirt gives each domain and a guest cannot choose).

## Options

**A. A vault Machine holding SSH keys, reached through a host relay that
asks for every signature (recommended).**

- The vault is a minimal Machine with no network interface at all. Its
  `ssh-agent` holds the keys; a small listener exposes the agent on one
  vsock port and nowhere else.
- A client Machine gets a socket at `SSH_AUTH_SOCK` that forwards to the
  host over vsock. Nothing else in it changes: `ssh` and `git` work as
  usual.
- The host relay accepts a connection, names the client by the vsock
  context id libvirt assigned to it (read from the domain's own
  definition, never from the guest), and passes only two agent requests:
  list identities, and sign. Adding, removing, locking or any extension is
  refused at the host and never reaches the vault.
- Each sign request stops at a host confirmation: which Machine asks, which
  key (fingerprint and comment), and the outcome. Without an answer in 30
  seconds it is refused. The operator may allow one Machine and one key for
  a few minutes, never for good.
- Git signs commits with SSH keys (`gpg.format=ssh`), so one mechanism
  covers both authentication and commit signing.

**B. Also split-GPG.** GnuPG's agent protocol is larger (decrypt, sign,
key listing with secret details), and HyperLab needs no GPG today. Later,
on the same relay, if a need appears.

**C. A hardware security key passed to each Machine.** Strong, but the key
must then move between Machines through USB passthrough (ADR 0034), and a
Machine holding it can use it without asking.

## Recommendation

A, SSH keys only.

## What is built first

The host side: `roles/host_vault` installs the relay
(`hyperlab-vault-relay`), its configuration (`/etc/hyperlab/vault.json`),
and the confirmation helper, a `hyprland-dialog` naming the Machine, key
fingerprint and comment as plain text with three buttons: Deny, Allow once,
Allow 5 minutes. A closed dialog, an unknown answer, a helper that does not
answer in time (killed with whatever it started) or no display is a
refusal. One question is on screen at a time. The relay is a user service
of the graphical session, because the operator answers there; its unit uses
only restrictions a user unit can apply without a user namespace, which the
hardened kernel refuses to unprivileged users.

A VM spec names a Machine's part with `key_vault`: `client` gives it a
vsock device next to its network; `vault` gives it the vsock device and no
interface at all, under the reserved network name `none`, which no image
can allow and only the vault may use. The vault is a permanent, standard,
Linux Machine configured by cloud-init, without the QEMU Guest Agent or the
clipboard: nothing reaches it after its first boot but its vsock port. The
domain XML guard compares the number of interfaces and vsock devices, so a
vsock device or an interface added to a live domain is drift.

The vault (`vm-specs/vault.yml`) is configured by its cloud-init alone. On
its first boot it makes its own ed25519 key, which never leaves it, and
loads it into an `ssh-agent` whose socket only its listener uses. The
listener (`hyperlab-vault-listen`) accepts only the host's context id and
passes only identity listing and signing, so a host relay that went wrong
still could not add, remove or lock keys. A client reads the public half
with `ssh-add -L` and the operator registers it where it is needed (GitHub,
`gpg.format=ssh` for commit signing). Importing an existing private key is
not offered: a key typed into a Machine has already left the vault's
protection.

A client Machine applies `playbooks/guest-vault-client.yml`: a user service
(`hyperlab-vault-agent`) listens at `$XDG_RUNTIME_DIR/hyperlab-vault.sock`,
the user's alone, and carries each connection unchanged to the host relay.
It decides nothing. It becomes the default `SSH_AUTH_SOCK` only when
`guest_vault_client_default_agent` is set, so a Machine that already uses
its own agent keeps it.

## What this does not cover

- A compromised client still gets each signature it is allowed: the
  confirmation shows which Machine and key, not what is signed.
- The vault's own compromise (its keys leave through no network, but a
  malicious key loaded into it would sign as asked).
- Keys typed or pasted into a Machine by hand.
- The host itself: a process of the operator's on the host can reach the
  vault's vsock port directly. The host is trusted throughout HyperLab.
- A client reaching the vault without the relay. HyperLab relies on
  vhost-vsock carrying a guest's packets only to the host and only with the
  guest's own context id; that has not been seen on HyperLab yet, and the
  hardware test below checks it before this ADR is accepted.

## Hardware test

In the lab host first, then on Nitro: a vault Machine with no interface
(`virsh domiflist` empty); `ssh -T git@github.com` from `dev-01` asks for
confirmation on the host and succeeds when allowed, fails when denied or
ignored; `ssh-add -D` from `dev-01` is refused at the host and the vault
keeps its keys; a connection from `dev-01` straight to the vault's context
id fails; a signed commit verifies with the vault's public key; the
private key is not readable anywhere but in the vault; the vault's key is
made on its first boot and the agent has it after a reboot; with
`guest_vault_client_default_agent` set, `SSH_AUTH_SOCK` in a login shell and
in the client's graphical session names the vault socket. `hyprland-dialog`
prints the button pressed on its standard output as the helper expects:
this has not been seen yet, and until it is, any other output is a refusal.
