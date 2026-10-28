# Contributing to hyperlab-ansible

This guide is for a change to this repository: the stage-2 Ansible roles,
playbooks, tools, the HyperLab shell and their tests. It explains how to
prepare a machine that can run the real checks, how to keep a change small
and refusal-first, and what evidence to hand to the maintainer.

Two kinds of report do not start here:

- **A security vulnerability** goes through the private route in
  [`SECURITY.md`](SECURITY.md), never a public issue or pull request. What
  HyperLab protects against, and what it does not, is in
  [`docs/threat-model.md`](docs/threat-model.md).
- **A hardware compatibility claim** ("it works on my laptop") is not made
  by a change here. Compatibility is recorded in `arch-hypervisor-lab`
  against an exact pair of `arch-bootstrap` and `hyperlab-ansible` commits;
  see [Hardware and compatibility](#hardware-and-compatibility).

## Repository map

| Path | What lives there |
| --- | --- |
| `roles/` | mechanisms: one responsibility per role |
| `group_vars/all/`, `host_vars/` | policy: shared intent, hardware profiles, networks |
| `playbooks/` | sequencing: broad targets and explicit lifecycle transactions |
| `images/`, `vm-specs/`, `service-specs/`, `templates/` | declared images, Machines, services and Templates |
| `schemas/` | the input contracts those declarations are validated against |
| `tools/` | Python and shell tools, `hyperlabctl` and its own suite |
| `tests/` | contracts, refusal suites, the render suite, bats protocols, fixtures and stubs |
| `release/` | the hardware acceptance manifest used by the release tooling |
| `docs/`, `docs/adr/` | operator guides and architecture decisions |
| `problems/` | write-ups of failures that changed a contract or an implementation |
| `verify.sh` | the whole local battery, one command |
| `.github/workflows/ci.yml` | the hosted CI jobs |

[`README.md`](README.md) and [`docs/playbooks.md`](docs/playbooks.md) explain
what the playbooks own; the ADR index is
[`docs/adr/README.md`](docs/adr/README.md).

## From clone to a green battery

1. Read this page, [`SECURITY.md`](SECURITY.md) and the security rules at
   the top of [`docs/roadmap.md`](docs/roadmap.md#security-rules-every-milestone-keeps).
2. Install the tools in [Setting up](#setting-up).
3. Clone and enter the repository, then install the two Ansible collections:

   ```bash
   git clone https://github.com/importriri/hyperlab-ansible.git
   cd hyperlab-ansible
   ansible-galaxy collection install -r collections/requirements.yml
   ```

4. Run one focused check for the area you will touch, for example
   `python tests/docs_contract.py` (see [Focused checks](#focused-checks)).
5. Run the complete battery, `./verify.sh`, before you change anything, so
   that you know what your machine reports on an unchanged tree.
6. Make the change, rerun the focused check, then `./verify.sh` again.

Every command above runs as your normal user. Level 2b of `./verify.sh` is
the only step that asks for a sudo credential, and only for one judge; see
[Level 2b and sudo](#level-2b-and-sudo).

**Do not run the host playbooks as test setup.** `playbooks/preflight.yml`,
`playbooks/lab.yml` and the other entrypoints under `playbooks/` reconfigure
the machine they run on: boot entries, VFIO, libvirt networks, the desktop.
None of them is needed to test a change, and none of them belongs on a
workstation that is not meant to become a HyperLab host. The tests run
against `localhost` with temporary directories and stubs.

## Setting up

### Platform assumptions

- The local battery is run on **Arch Linux x86_64**, the distribution the
  project targets. `verify.sh` itself suggests `pacman` when a tool is
  missing.
- The hosted CI job runs on a GitHub-hosted **Ubuntu 26.04** runner
  (`runs-on: ubuntu-26.04` in `ci.yml`), where `/bin/sh` is dash; on Arch it
  is bash. A shell script that only passes under one of them is a defect.
- Other distributions are not tested. They may work with equivalent
  packages; a failure there is still worth reporting with its output.
- You do not need a HyperLab host, a GPU, libvirt or a VM to run the
  battery.

### Packages

`verify.sh` stops early with `Missing collections` or `Missing tools:` and
names five tools. That message is only its first precondition: the
contracts it discovers need more, and a tool missing from the message shows
up later as a failing contract that names it (for example
`lspci (pciutils) is needed to compare the sysfs reading`) or as a
`SKIPPED` line. The table below is derived from `verify.sh`, the `ci.yml`
install step and the tools the contracts call.

| Needed for | Arch package | CI (Ubuntu) equivalent |
| --- | --- | --- |
| `ansible-playbook`, `ansible-galaxy` (levels 1, 2a, 2b and contracts that run playbooks) | `ansible` | `pip install --user ansible` |
| level 0i | `ansible-lint` | `pip install --user ansible-lint` |
| level 0h | `ruff` | `pip install --user ruff` |
| level 0a, rendered helpers in 2b | `shellcheck` | `shellcheck` |
| level 3 | `bats` | `bats` |
| every Python check; PyYAML and Jinja2 are imported directly by the contracts | `python`, `python-yaml`, `python-jinja` | runner Python, pulled in with `ansible` |
| the privileged `nft -c` judge in 2b | `nftables` | `nftables` |
| `visudo -cf` in 2b | `sudo` | runner default |
| `luac` in 2b and the Lua checks of the guest shell contracts | `lua` | `lua5.4` |
| `pdfinfo`, `pdftoppm` (`tests/safe_pdf_contract.py`) | `poppler` | `poppler-utils` |
| building the Looking Glass sender code in its contracts | `gcc`, `pkgconf`, `libpipewire`, `glib2` | runner `gcc`, `pkg-config`, `libpipewire-0.3-dev`, `libglib2.0-dev` |
| `lspci` (`tests/foundation_check_mode_contract.py`) | `pciutils` | `pciutils` |
| offscreen QML runtime contracts (Qt 6 `qmlscene`, QtQuick, Window, Shapes, WorkerScript) | `qt6-declarative` | `qmlscene-qt6` and four `qml6-module-*` packages |
| `openssl`, `git`, `modprobe` | `openssl`, `git`, `kmod` | runner defaults |

On Arch, in one step:

```bash
sudo pacman -S --needed ansible ansible-lint ruff shellcheck bats \
  python python-yaml python-jinja nftables sudo lua poppler \
  gcc pkgconf libpipewire glib2 pciutils qt6-declarative \
  openssl git kmod
```

Package names were checked against the official package search,
<https://archlinux.org/packages/>; look a name up there again if `pacman`
does not find it. `ansible-galaxy collection install` fetches
`community.general` and `community.libvirt` from Ansible Galaxy, so that
step needs the network; the checks themselves do not fetch anything.

An optional tool widens a check instead of failing it when it is absent:
`apparmor_parser` compiles the QEMU AppArmor profile in
`tests/qemu_apparmor_contract.py`.

## The checks

### Focused checks

Run the narrowest check that covers your change while you work:

| Area | Command |
| --- | --- |
| one contract | `python tests/<name>_contract.py` |
| a refusal suite | `ansible-playbook -i inventory.ini tests/<name>-refusals.yml` |
| the render suite without its root-only judge | `ansible-playbook -i inventory.ini tests/render.yml --skip-tags privileged` |
| a bats protocol | `bats tests/<name>.bats` |
| `hyperlabctl` | `PYTHONDONTWRITEBYTECODE=1 python tools/hyperlabctl/tests/run.py` |
| shell structure | `sh tools/shell-tests/run.sh` |
| one playbook's syntax | `ansible-playbook --syntax-check -i inventory.ini playbooks/<name>.yml` |
| Python lint | `ruff check <path>` |

A focused check is for speed. It does not replace `./verify.sh`.

### What `./verify.sh` runs

Run it from the repository root. Each level prints `OK`, or `FAIL` with the
last 25 lines of the failing command.

| Level | What it runs |
| --- | --- |
| 0a | `shellcheck` on every file with a shell shebang, found by search |
| 0b | `tests/static_contract.py` |
| 0c | `tests/schema_validate.py`: image manifests and VM specs against `schemas/` |
| 0d | `tests/schema_mutations.py` and `tests/contract_mutations.py` |
| 0e | every `tests/*_contract.py`, discovered |
| 0f | `sh tools/shell-tests/run.sh` (no display required) |
| 0g | the palette audit, the surface check and the three choices checks under `tools/` |
| 0h | `ruff check .` with the repository's `ruff.toml` |
| 0i | `ansible-lint` with the `production` profile from `.ansible-lint` |
| 1 | `ansible-playbook --syntax-check` on every `playbooks/*.yml` |
| 2a | every `tests/*-refusals.yml` |
| 2b | `tests/render.yml`, the render and invariant suite |
| 3 | every `tests/*.bats` |

Discovery means a new contract, refusal suite, playbook or bats file is
picked up without editing the verifier. Levels 0a and 0i look at the files
in your working tree, not only the tracked ones: a scratch script or a YAML
copy left in the checkout is checked too.

The run ends with one of three lines:

- `ALL GREEN - ready to commit.` and exit status 0: every level ran,
  including the privileged judge, and passed.
- `VERIFICATION INCOMPLETE` and exit status 1: everything that ran passed,
  but the `nft -c` judge did not run because there was no sudo credential.
- `VERIFICATION FAILED` and exit status 1: at least one check failed. A
  failure is always reported as a failure, even when the judge was missing
  as well.

### Level 2b and sudo

`tests/render.yml` renders every brick's files into a temporary directory
and checks them. One task, `nft -c` on the rendered ruleset, needs root
because it opens a netlink socket; it carries the `privileged` tag. The
verifier looks for a credential in this order:

1. `PRIVATESTACK_BECOME_PASSWORD_FILE` names a readable file; an unreadable
   one is a failure, not a fallback;
2. an interactive terminal: it asks up to three times, validates the
   password with `sudo`, and hands it to Ansible through a private,
   short-lived file under `$XDG_RUNTIME_DIR` that it removes afterwards;
3. sudo that already works without a password.

With none of them it runs every other render invariant with
`--skip-tags privileged`, prints
`NOT RUN - the privileged nft -c judge of tests/render.yml (no sudo credentials)`
and ends `VERIFICATION INCOMPLETE`. `tests/verify_render_selection_contract.py`
checks each of these paths with recording stubs.

Two results must not be confused:

- **The unprivileged diagnostic run.** Without sudo you can still run the
  whole battery and learn whether anything else fails. That run is
  incomplete: report it with its `NOT RUN` line and exit status 1, never
  as green. The missing judge is the only gap this run may have.
- **The full qualification run.** A change is qualified only by a run that
  ends `ALL GREEN`, with the judge executed. If you cannot produce one, say
  so; the maintainer runs it.

For the full run, prefer the interactive prompt. If you use a password file,
keep it outside the repository, readable only by you, and delete it after
the run. Do not add a passwordless sudo rule for the verifier, do not put a
password in a command line, an environment variable's value, a log, a
commit or an issue attachment, and do not remove or retag the `privileged`
task to make a run green.

### Blockers are not skips

Some contracts open local UNIX sockets or allocate a pseudo-terminal,
others drive stubbed operations through child processes, and the Ansible
levels run `ansible-playbook` against `localhost` over its local
connection. In a restricted sandbox or container these fail with errors
such as `PermissionError: [Errno 1] Operation not permitted`, a PTY
allocation error, a read-only file system (`EROFS`), or a contract's own
message that a stubbed run did not succeed. These are failures of the
environment, and they block the change until the battery runs in an
environment that allows them. They are not an accepted skip, and neither
is any failure outside the 2b judge.

A few checks do skip honestly when an optional input is absent, and say so
on their own output line while the level still prints `OK`:

- `tests/cross_repo_contract.py` prints `SKIPPED` and "nothing was checked"
  without an `arch-hypervisor-lab` checkout (see
  [Sibling repositories](#sibling-repositories));
- the offscreen QML contracts print `SKIPPED` without Qt 6 `qmlscene`. Set
  `HYPERLAB_REQUIRE_QML_RUNTIME=1` to turn its absence into a failure;
- some contracts check less without `luac`, `modprobe` or
  `apparmor_parser`.

A skipped part proved nothing. Install what it needs when your change
touches that area, and mention any skip in your report. Run a single
contract by hand to see its full output.

### CI and the local battery

The `validate` job in `ci.yml` runs the same families of checks on Ubuntu,
including the shell-structure suite of level 0f and the five palette and
choices checks of level 0g. Their parity with `verify.sh` is itself checked:
`tests/ci_verify_parity_contract.py` executes both files with recording
stubs and compares the commands. The two runs are still not identical:

- CI runs the steps in a different order and skips the remaining steps
  after the first one that fails; `verify.sh` runs every level and reports
  every failure;
- CI runs the render suite with the runner's passwordless sudo, so the
  `nft -c` judge runs there;
- CI's `/bin/sh` is dash;
- CI does not set `HYPERLAB_REQUIRE_QML_RUNTIME`; it installs Qt 6 instead;
- a separate `cross-repo` job checks out `arch-hypervisor-lab` and runs the
  hardware-profile comparison with `CROSS_REPO_REQUIRED=1`, so it may not
  skip there.

A green CI run is a software result for one commit. It does not replace a
local `ALL GREEN`, and neither of them is a hardware result. A level that a
CI run did not execute, for instance in a run of an older workflow, is
unverified for that commit until `./verify.sh` runs it. On a failure,
CI keeps the ansible-lint, structural-contract and render logs as workflow
artifacts for three days.

## Making a change

### Put it in the right place

- **Roles own mechanisms**: how a thing is done.
- **Checked-in data owns policy**: what is allowed, in `group_vars/`,
  `host_vars/`, specs and manifests, validated by `schemas/`.
- **Playbooks own sequencing**: what runs in which order. Image import,
  VM creation and destruction, service registration and recovery stay
  explicit transactions; host reconciliation never creates or destroys a
  workload.

A change that shapes the architecture is proposed as an ADR in `docs/adr/`,
in the format of the recent records, with `Status: proposed.` below its
title and an entry in the index. The maintainer accepts or rejects it.

### Refusal first

Every change keeps the security rules in
[`docs/roadmap.md`](docs/roadmap.md#security-rules-every-milestone-keeps).
In practice:

- write the refusal before the success path, and test it first;
- fail closed: a missing, unreadable, duplicated or redirected input is a
  refusal, never a default;
- nothing is adopted implicitly: an existing disk, image, Template or
  libvirt domain does not become HyperLab's because it is there;
- a guest's own claims never raise its trust.

### Tests that prove behaviour

A test proves behaviour when it runs the code or parses the artifact, and
compares the result with an **independent oracle**: the real judge
(`visudo -cf`, `nft -c`, `shellcheck`, `luac`), a value computed separately
from the code under test, or the parsed structure of YAML, JSON, XML, the
Python AST or the real argv. Reading that a substring is present proves only
that the text is there; a weakened condition next to it survives. Some older
contracts still match text; do not copy that pattern into a new test.

Tests use temporary directories, fixtures (`tests/fixtures/`) and stubs
(`tests/quickshell_stubs/`, recording stubs in the contracts). A test must
not touch a live Machine registry, libvirt, storage or the host's
configuration, and must not call the real `sudo` or `virsh`: record the
argv a stub receives instead. The 2b judge is the one privileged check,
and it only reads a rendered file.

### Seeing a check fail

A check that has never been seen red proves nothing. When you add or
change an invariant:

1. predict which check must fail and with which message;
2. break the invariant in a disposable copy of the repository, such as a
   scratch clone of your branch, never in the working tree with your
   uncommitted work;
3. run the predicted check: it must fail where you said;
4. restore the file and run it again: it must pass.

Record the mutation in the catalogue the area already uses:
[`tests/MUTATIONS.md`](tests/MUTATIONS.md),
[`tools/hyperlabctl/MUTATIONS.md`](tools/hyperlabctl/MUTATIONS.md), or the
automated cases in `tests/contract_mutations.py`. A mutation that stays
green is reported as green, with the reason, not dropped. A prose-only
change needs no new test and no mutation; `./verify.sh` still runs.

### Write up the non-obvious defect

When you find and fix a defect whose cause was not obvious, add a note in
`problems/`: what was seen, what was actually wrong, the fix and the
regression proof, as the existing notes do. List it once in
[`problems/README.md`](problems/README.md);
`tests/docs_contract.py` refuses a missing or duplicated entry. A problem
that stays open is also listed in the threat model, which
`tests/threat_model_contract.py` checks.

### Keep the documentation true

Change the documentation of the behaviour you change in the same commit.
Words about evidence have levels: "software-verified" means the tests
prove it; hardware claims ("on Nitro", "Predator-verified") belong to the
maintainer's evidence process, and roadmap boxes that report hardware stay
as they are. `tests/docs_contract.py` checks the local links of `README.md`,
`docs/` and the `hyperlabctl` README, the problem index and the evidence
form of checked hardware boxes.

## Sibling repositories

HyperLab is three repositories. `arch-bootstrap` installs the encrypted
base, this repository configures the host, and `arch-hypervisor-lab`
records sanitized hardware evidence. Keep separate clones; the checks here
read a sibling checkout, never write to it and never fetch one.

- **Hardware profiles.** When you change `host_profiles` in
  `group_vars/all/hardware.yml`, compare them with the compatibility record
  and pass the checkout explicitly:

  ```bash
  python tests/cross_repo_contract.py ../arch-hypervisor-lab
  ```

  It ends `cross-repo contract: OK` with the number of profiles compared.
  Without a path it falls back to `ARCH_HYPERVISOR_LAB` or a
  `../arch-hypervisor-lab` that holds `hardware/compatibility.yml`, and
  otherwise prints `SKIPPED`: nothing was compared.
- **Storage hand-off.** The VM-store contract that `arch-bootstrap` writes is
  validated here by `tools/bootstrap_storage_guard.py` and listed in
  `allowed_storage_topologies` of `release/acceptance.v2.yml`. When you
  change either, run the comparison from an `arch-bootstrap` checkout
  against yours:

  ```bash
  cd ../arch-bootstrap
  HYPERLAB_ANSIBLE_REPO=/path/to/hyperlab-ansible \
    CROSS_REPO_STORAGE_REQUIRED=1 bash verify.sh
  ```

  Without those variables that verifier reports the comparison as skipped.
  Its own guide, `docs/release-gates.md` in `arch-bootstrap`, describes what
  the comparison does and does not prove.

A sibling change is a separate contribution to that repository.

## Material you add or keep

- **Caches** stay out of Git: `__pycache__/`, `.ansible/`, `.cache/` and
  `*.retry` are ignored; downloaded collections live outside the checkout.
- **Synthetic keys, logs and fixtures** are made for the test, look
  synthetic and are created in a temporary directory at run time where
  possible. A real key, password, host name, address, serial number or
  account never becomes a fixture.
- **Private hardware material** (raw logs, receipts, screenshots, disk
  images, home-directory paths) stays with whoever produced it. A public
  contribution never needs it, and nobody will ask you to attach it.
- **Imported material** (code, patches, images, fonts, themes, text) needs
  its origin (URL and exact version or commit), the licence that applies to
  it and its upstream notices, kept unchanged. State them in the change's
  description and commit message. Do not claim authorship of it and do not
  relicense it. If you cannot name its origin and terms, do not submit it.
  The current record of file origins and third-party licences is
  [`docs/third-party-licences.md`](docs/third-party-licences.md).

## Proposing a change

Propose a change as a pull request against `main`. Keep one concern per
change, small enough to review in one sitting, and each commit green.
Follow the existing commit style: an imperative subject with a capital
first letter, no type prefix, no final period and at most 72 characters,
and a body that explains why.

Give the maintainer the evidence with the change:

- the commit the change is based on;
- what changed and why, and which security rule or ADR it touches;
- the focused checks you ran, with their output;
- the final line of `./verify.sh`: `ALL GREEN`, or `VERIFICATION INCOMPLETE`
  with its `NOT RUN` line when you had no sudo credential;
- for a new or changed invariant: the mutation, the check you predicted,
  the red message you saw and the green rerun;
- every `SKIPPED` line that touches your change, and every sibling check
  you ran or could not run;
- what you could not verify, and why.

For a failure you cannot solve, the useful diagnostic is the exact command,
the `FAIL` block `verify.sh` printed (or the single contract's full output),
the commit, and the versions of the tools involved (`ansible --version`,
`python --version`). Before you paste anything, remove user and host names,
home paths, addresses, serial numbers, keys, passwords and tokens.

## Hardware and compatibility

Software checks cannot certify a laptop. Hardware evidence binds a result to
the exact `arch-bootstrap` and `hyperlab-ansible` commits of an acceptance
campaign, run on the named machine in the order of
[`docs/release-evidence.md`](docs/release-evidence.md), and is published as
sanitized evidence in `arch-hypervisor-lab`. A change here does not add or
raise a compatibility status, and a report from another laptop is an
observation, not a campaign. Hardware gates, compatibility claims and
releases remain with the maintainer.

## Security reports

Use GitHub's private vulnerability reporting, as
[`SECURITY.md`](SECURITY.md) says. Whether that form is enabled is a
repository setting this guide cannot check. If it does not open for you,
GitHub's documentation on
[reporting privately](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)
suggests opening an issue that only asks the maintainer for a security
contact; put no detail of the vulnerability in it.
