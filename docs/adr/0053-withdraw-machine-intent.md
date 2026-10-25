# ADR 0053 - A Machine is created in one staged step, and withdrawn only by its digest

Status: proposed.

## Context

ADR 0017 says a refused creation leaves no record behind. The bridge has to
record a Machine (`hyperlabctl machine create`, which writes the record) and
project it (`machine project`, which writes the generated spec). When the
projection refuses after the record was written, the record has to go, or a
retry is refused with "already exists" for a Machine the shell was told was
not created.

The registry is the only source of product membership
(`tools/hyperlabctl/README.md`): a libvirt domain without a record is not a
product Machine. A command that removes records can therefore take a live
domain out of the product if it is not held to the Machine's state.

## Options

**A. Stage the creation, publish the record last (recommended for the
shell).** `machine create --project`, under the registry lock, checks that
the name is free, writes the generated spec, and only then publishes the
record. When the record cannot be published, it removes the spec it wrote,
and only while that file is still the one it wrote, with its bytes. The
publication is not the end of the step: the record is synced, read back and
its digest compared with the one published. The publication names its
file before `os.link`, so a failure there, a handled cancellation
included, undoes the record this step published (same inode, same bytes)
under the same lock,
and only then the spec, so the undo never leaves a record without its
spec. When the undo cannot finish, the refusal says "cleanup incomplete"
and names what stays; bytes this step did not write are kept. A creation
killed between the two writes leaves a spec without a record, and the next
request for that name is refused with "already exists" by the spec. None
of this is atomic across process death or power loss.

**B. Two calls, and withdraw the record when `project` refuses.** This was
the first implementation. It needs a command that removes a published
record, and that command must refuse whenever it cannot prove the record is
only intent: a projection equal to the record's, a libvirt domain with its
name, a domain list it cannot read. Each of those refusals then left the
record behind after a refused creation. Rejected for the shell.

**C. Check what `project` would refuse before calling `create`.** The
bridge would copy the projection's rules and could still be overtaken
between the check and the write. Rejected.

## Withdraw stays, for the manual path

`docs/first-machine.md` keeps `create` and `project` as two commands, and
there a refused `project` leaves intent behind. `machine create` reports
the SHA-256 of the record it stored, and `machine withdraw ID
--record-sha256 DIGEST` removes the record only while:

- its stored bytes still have that digest, so a record written or changed
  by anything else is not removed in its place;
- no generated spec equal to its projection exists, and a spec that
  cannot be read as exactly one YAML mapping (a link, not a regular file,
  unreadable, malformed, several documents, a repeated key), or a
  generated directory that is a link, even a dangling one, is a refusal,
  never taken for an absent or a stale one;
- the libvirt domain list, read at that moment, has no domain with its
  name, and the list could be read at all.

The digest names a record; it is not an authorization: anyone who can read
the record can compute it. What protects a Machine that went further is the
projection and domain checks, which do not depend on who calls.

`create`, `project` and `withdraw` hold an exclusive lock on the registry
(`$XDG_STATE_HOME/hyperlab/machines/.lock`) across their checks and writes.
A lock that stays held for five seconds is a refusal, not a wait without
end.

## Recommendation

A for the shell, and `withdraw` as above for the manual path.

## What this does not cover

- Removing a Machine that has a domain. That is `vm-destroy.yml` and the
  domain's own lifecycle; `withdraw` refuses it.
- Operation records of `machine.provision`. A creation that reached the
  operation runner has a projected spec, which `withdraw` already refuses.
- A record and spec left by an interrupted provisioning, with no domain,
  and a spec left by a creation killed between its two writes: nothing in
  the shell removes them yet. By hand, `hyperlabctl compose delete NAME
  --confirm NAME` removes the spec and then `machine withdraw` the record;
  both refuse while a domain with that name exists.

## Hardware test

On Nitro, as the user, with the bridge installed:
`privatestack-machine-actions create server-arch NAME permanent dev balanced`
with a directory in the way at `vm-specs/.generated/NAME.yml` is refused
with "already exists", and `hyperlabctl machine show NAME` fails: no record.
For a Machine with a defined domain, move its generated spec aside, run
`hyperlabctl machine withdraw NAME --record-sha256` with the record's
`sha256sum`, then move the spec back: refused with "a libvirt domain named
NAME exists", and `hyperlabctl machine show NAME` still answers.
