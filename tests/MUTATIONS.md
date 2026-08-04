# MUTATIONS.md - the firing range

A test that has never been seen red proves nothing. Every invariant in
this repo earned its place by catching a deliberate breakage before it
was frozen. This is the catalog: for each mutation, the exact command
that breaks the repo, the check that MUST turn red, and the restore.

Replaying one is step 6 of the pre-push ritual:

1. **Predict** which check dies - say it before running anything.
2. Apply the Break command.
3. `./verify.sh` - it must FAIL, where you predicted.
4. Restore. `./verify.sh` - all green again.

Restores assume git (`git checkout -- <file>`, which also restores the
executable bit). Before the first commit, keep a plain copy instead
(`cp <file> /tmp/bak`) - and after restoring the hook that way, re-run
`chmod +x` (the first bats test will remind you if you forget).

The original twenty-six were executed and caught during the build. New
cross-repository contract mutations are listed below and should be replayed as
the hardware-profile pipeline is validated. Replay at least one before every
push.

## roles/base + the shared contract

### 1. Strict rp_filter
- Break: `sed -i 's/net.ipv4.conf.all.rp_filter = 2/net.ipv4.conf.all.rp_filter = 1/' roles/base/files/99-hardening.conf`
- Red: render suite, "A hardening invariant broke" - five bridges need
  loose mode; strict drops legitimate asymmetric paths.
- Restore: `git checkout -- roles/base/files/99-hardening.conf`

### 2. Broken sudoers drop-in
- Break: `printf '%%wheel ALL=(ALL:ALL NOPASSWD ALL\n' > roles/base/files/10-wheel`
- Red: render suite - the real judge (`visudo -cf`) rejects the file.
- Restore: `git checkout -- roles/base/files/10-wheel`

### 3. services joins the GPU rotation
- Break: `sed -i 's/^  lab: 0$/  lab: 0\n  services: 2/' group_vars/all/networks.yml`
- Red: render suite - contract invariants ("services never joins it").
- Restore: `git checkout -- group_vars/all/networks.yml`

## roles/kvm_host

### 4. qemu-desktop sneaks into the package list
- Break: `sed -i 's/^  - qemu-base$/  - qemu-desktop/' roles/kvm_host/defaults/main.yml`
- Red: render suite - kvm_host invariants. Structural check: the YAML
  is parsed and the actual list inspected, so comments cannot trip it
  (they did once - see the A2 review).
- Restore: `git checkout -- roles/kvm_host/defaults/main.yml`

## roles/vfio_boot

### 5. Backslash continuation in a boot entry
- Break: `sed -i 's|^options zswap.enabled=0$|options zswap.enabled=0 \\|' roles/vfio_boot/templates/entry.conf.j2`
- Red: render suite - boot entry invariants. The Boot Loader Spec has
  no continuations: the loader drops the orphan line silently and the
  machine still boots, missing parameters.
- Restore: `git checkout -- roles/vfio_boot/templates/entry.conf.j2`

### 6. cryptdevice instead of rd.luks.name
- Break: `sed -i 's|rd.luks.name={{ vfio_boot_luks_uuid }}={{ luks_mapper_name }}|cryptdevice=UUID={{ vfio_boot_luks_uuid }}:{{ luks_mapper_name }}|' roles/vfio_boot/templates/entry.conf.j2`
- Red: render suite - wrong initramfs dialect; sd-encrypt would ignore
  it in silence and park the boot in the initramfs.
- Restore: `git checkout -- roles/vfio_boot/templates/entry.conf.j2`

### 7. Duplicate kernel parameter key
- Break: `sed -i 's|"nvidia-drm.modeset=1 modprobe.blacklist=nouveau"|"nvidia-drm.modeset=1 modprobe.blacklist=nouveau rw"|' roles/vfio_boot/defaults/main.yml`
- Red: render suite - duplicate-key detection (`rw` already lives on
  the contract-composed root line).
- Restore: `git checkout -- roles/vfio_boot/defaults/main.yml`

## roles/network_domains

### 8. The lab receives a forward element
- Break: `sed -i "s|{% if item.forward == 'nat' %}|{% if true %}|" roles/network_domains/templates/net.xml.j2`
- Red: render suite - the strict boolean equivalence
  (isolated <=> no `<forward>` at all).
- Restore: `git checkout -- roles/network_domains/templates/net.xml.j2`

### 9. Truncated XML
- Break: `sed -i 's|</network>||' roles/network_domains/templates/net.xml.j2`
- Red: render suite - the real judge (python `ET.parse`) dies with a
  ParseError before any assert is even reached.
- Restore: `git checkout -- roles/network_domains/templates/net.xml.j2`

## roles/lab_isolation

### 10. flush ruleset as a real directive
- Break: `sed -i 's|^flush table inet lab_isolation$|flush ruleset|' roles/lab_isolation/templates/lab-isolation.nft.j2`
- Red: render suite - matrix invariants. **Note:** `nft -c` BLESSES
  this mutation (valid syntax); only the anchored semantic pin catches
  it. This single mutation justifies the whole level-2 layer.
- Restore: `git checkout -- roles/lab_isolation/templates/lab-isolation.nft.j2`

### 11. Halved deny matrix
- Break: `sed -i 's|{% if a.name != b.name %}|{% if a.name < b.name %}|' roles/lab_isolation/templates/lab-isolation.nft.j2`
- Red: render suite - pair count no longer equals n*(n-1).
- Restore: `git checkout -- roles/lab_isolation/templates/lab-isolation.nft.j2`

### 12. restart instead of reload
- Break: `sed -i 's|state: reloaded|state: restarted|' roles/lab_isolation/handlers/main.yml`
- Red: render suite - reload-only pin (on Arch the unit's stop action
  flushes the whole ruleset: a restart wipes libvirt's NAT).
- Restore: `git checkout -- roles/lab_isolation/handlers/main.yml`

## roles/gpu_handoff

### 13. Inverted trust ladder
- Break: `sed -i 's/trust > current/trust < current/' roles/gpu_handoff/files/qemu`
- Red: bats - three tests at once (downgrade, lateral, upgrade-refused).
- Restore: `git checkout -- roles/gpu_handoff/files/qemu`

### 14. Phase guard removed
- Break: `sed -i '/== "prepare"/d' roles/gpu_handoff/files/qemu`
- Red: bats - "non-prepare phases pass instantly, even for an upgrade".
- Restore: `git checkout -- roles/gpu_handoff/files/qemu`

### 15. services rendered into the rotation
- Break: `sed -i 's/{% endfor %}/{% endfor %}\nservices 2/' roles/gpu_handoff/templates/rotation.j2`
- Red: render suite - rotation invariants ("services never joins it",
  and the line count no longer matches the contract map).
- Restore: `git checkout -- roles/gpu_handoff/templates/rotation.j2`

## roles/desktop - the cockpit rice

### 16. Helper deployed 0644
- Break: `sed -i '0,/mode: "0755"/s//mode: "0644"/' roles/desktop/tasks/main.yml`
- Red: render suite, "A rice invariant broke" - a config file copied 0644
  is inert, a SCRIPT copied 0644 is a silent no-op: waybar shows an empty
  module and nothing anywhere says why.
- Restore: `git checkout -- roles/desktop/tasks/main.yml`

### 17. rofi launcher theme points at a name nobody deploys
- Break: `sed -i 's/@theme "rofi-launcher.rasi"/@theme "launcher.rasi"/' roles/desktop/files/rofi-config.rasi`
- Red: `rofi_theme_contract.py` - the launcher must replace the stock theme
  with the exact file deployed by the desktop role. Replacing `@theme` with
  `@import` is also refused because it brought back the light fallback rows
  and broke Mod+D on the Nitro.
- Restore: `git checkout -- roles/desktop/files/rofi-config.rasi`

### 17a. rofi selection follows the mouse again
- Break: `sed -i 's/hover-select:        false/hover-select:        true/' roles/desktop/files/rofi-config.rasi`
- Red: `rofi_theme_contract.py` - keyboard selection must stay stable instead
  of jumping whenever the pointer crosses a row.
- Restore: `git checkout -- roles/desktop/files/rofi-config.rasi`

### 18. Backdrop path drift
- Break: `sed -i 's#backgrounds/privatestack/mocha#backgrounds/mocha#' roles/desktop/files/sway.config`
- Red: render suite, "A rice invariant broke" - one wallpaper, three
  files that name it (copy task, sway.config, swaylock.conf). Two out of
  three agreeing is a black desktop or a black lock screen.
- Restore: `git checkout -- roles/desktop/files/sway.config`

### 19. cava emits levels the bridge cannot map
- Break: `sed -i 's/ascii_max_range = 7/ascii_max_range = 15/' roles/desktop/files/cava-waybar.conf`
- Red: render suite, "A rice invariant broke" - the bridge script maps
  0-7 onto the eighth-block glyphs; raise the range and the extra levels
  reach waybar as bare digits.
- Restore: `git checkout -- roles/desktop/files/cava-waybar.conf`

### 20. The old launcher comes back
- Break: `sed -i 's/^  - rofi$/  - rofi\n  - fuzzel/' roles/desktop/defaults/main.yml`
- Red: render suite, "A cockpit invariant broke" - one launcher, and it
  is the one the sway binding and the power menu actually call. The same
  assertion refuses `rofi-wayland`: rofi 2.0 Provides/Replaces it, pacman
  resolves that but `pacman -Q` does not, so the module would report
  changed on every run forever.
- Restore: `git checkout -- roles/desktop/defaults/main.yml`

## roles/looking_glass

### 21. Frame geometry moved, shared memory left behind
- Break: `sed -i "s/^looking_glass_width: 1920$/looking_glass_width: 3840/" roles/looking_glass/defaults/main.yml`
- Red: render suite - Looking Glass invariants (the sizing formula now
  yields 64 MiB). The coupling is the point: the guest XML ivshmem size
  has to move with it, so the test refuses to let the geometry change
  quietly on one side only.
- Restore: `git checkout -- roles/looking_glass/defaults/main.yml`

### 22. udev retrigger dropped
- Break: `sed -i '/--action=change/d' roles/looking_glass/handlers/main.yml`
- Red: render suite - Looking Glass invariants. `udevadm control --reload`
  on its own applies to devices that appear *later*; the kvmfr node
  already exists, so without the synthetic change event the rule is a
  no-op and QEMU or the client is left with EACCES.
- Restore: `git checkout -- roles/looking_glass/handlers/main.yml`

### 23. X11 back in the client
- Break: `sed -i 's/-DENABLE_X11=no/-DENABLE_X11=yes/' roles/looking_glass/tasks/main.yml`
- Red: render suite - Looking Glass invariants. Same contract as the
  cockpit: the whole path is Wayland, and a client that can still fall
  back to X11 lets that rot silently.
- Restore: `git checkout -- roles/looking_glass/tasks/main.yml`

### 24. window_type goes back to being a regex
- Break: `sed -i 's/^for_window \[window_type="dialog"\].*$/for_window [window_type="dialog|menu"]/; /^for_window \[window_type="menu"\]/d' roles/desktop/files/sway.config`
- Red: render suite, "A rice invariant broke" - the line above it takes a
  regex (`window_role`), this one does not: sway matches `window_type`
  with `strcasecmp` against a fixed list, an unknown value leaves the
  criteria empty, and sway refuses the whole line at startup with
  "Criteria is empty". Caught on hardware first; this is the check that
  keeps it caught.
- Restore: `git checkout -- roles/desktop/files/sway.config`

### 25. The stamp directory is never declared
- Break: delete the `Own the stamp directory` task from
  `roles/looking_glass/tasks/main.yml`
- Red: render suite - Looking Glass invariants. `copy` does not create
  parent directories and upstream `make install` does not create
  `/usr/local/share/looking-glass`, so the run compiles the whole client
  and then dies on the last task - the stamp, which is the idempotency.
  The next run recompiles from scratch, forever.
- Restore: `git checkout -- roles/looking_glass/tasks/main.yml`

### 26. A top-level fact creeps back in
- Break: `sed -i "s/ansible_facts\['processor_vcpus'\]/ansible_processor_vcpus/" roles/looking_glass/tasks/main.yml`
- Red: render suite - Looking Glass invariants. `INJECT_FACTS_AS_VARS`
  defaults to true today and is deprecated: at ansible-core 2.24 the
  top-level name stops existing and `make -j` silently falls back to the
  default. A deprecation warning is a dated bug report.
- Restore: `git checkout -- roles/looking_glass/tasks/main.yml`

## Hardware and reconciliation contracts

### 27. Predator profile loses the HDMI-audio function
- Break: `sed -i '/10de:228b/d' group_vars/all/hardware.yml`
- Red: static contract, "predator-3070 must bind GPU and HDMI audio".
- Restore: `git checkout -- group_vars/all/hardware.yml`

### 28. Persistent network drift is no longer read
- Break: `sed -i 's/net-dumpxml --inactive/net-dumpxml/' roles/network_domains/tasks/main.yml`
- Red: static contract, "network drift must compare persistent XML".
- Restore: `git checkout -- roles/network_domains/tasks/main.yml`

### 29. Existing libvirt networks stop receiving persistent XML updates
- Break: replace the `virsh net-define` command in
  `roles/network_domains/tasks/main.yml` with `community.libvirt.virt_net`
  using `command: define`.
- Red: static contract, "network reconciliation must update persistent XML with virsh net-define".
- Restore: `git checkout -- roles/network_domains/tasks/main.yml`

### 30. Looking Glass comments regress to hash markers
- Break: `sed -i '1s/^;/#/' roles/looking_glass/templates/client.ini.j2`
- Red: static contract, "Looking Glass B7 comments must use semicolons".
- Restore: `git checkout -- roles/looking_glass/templates/client.ini.j2`

### 31. kvmfr unload failures are ignored again
- Break: `sed -i 's/failed_when: looking_glass_unload.rc != 0/failed_when: false/' roles/looking_glass/handlers/main.yml`
- Red: static contract, "kvmfr resize must fail when unload fails".
- Restore: `git checkout -- roles/looking_glass/handlers/main.yml`

### 32. Nitro gate starts prompting for every Ansible invocation again
- Break: add `-K` back to an `ansible-playbook` command in
  `run-nitro-m9-cockpit-gate.sh`.
- Red: Nitro gate contract, "ansible-playbook -K" must remain absent.
- Restore: `git checkout -- run-nitro-m9-cockpit-gate.sh`

## Image store (M2)

Run each mutation from a clean tree, execute the named test, then restore the
file before trying the next mutation. The important property is not the number
of mutations; it is that each safety claim has a test capable of becoming red.

### 51. A write enters pre-write validation
- Break: append an `ansible.builtin.file` task to
  `roles/image_store/tasks/validate.yml`.
- Red: `python tests/image_store_contract.py` — `validate.yml` is read-only and
  has no exemption for the module most likely to create a directory by mistake.

### 52. A new shell-out bypasses the exact allowlist
- Break: add any `ansible.builtin.command` task, or change an allowlisted
  executable to `/bin/true`.
- Red: structural contract — no shell is permitted and command is limited to
  `/usr/bin/readlink`, `/usr/bin/test` and `/usr/bin/lsattr`, all using `argv`
  with `changed_when: false`.

### 53. Canonicalisation is removed
- Break: remove the `readlink -m` task from `validate.yml`.
- Red: structural contract and refusal `ancestor-symlink`.

### 54. A mount-boundary post-check disappears
- Break: remove `stat.dev` from the post-creation assertion in `main.yml`.
- Red: structural contract — device IDs must be checked before and after the
  create window.

### 55. An unresolved libvirt build default is accepted
- Break: remove `Refuse unresolved runtime identities` from `identity.yml`.
- Red: refusal `unresolved-runtime-identity` and the structural sentinel check.

### 56. A missing administrator identity passes getent
- Break: select on result `failed` after leaving `failed_when: false` on the
  getent loop.
- Red: refusal `nonexistent-administrator` and the structural check requiring
  the getent fact map to be inspected.

### 57. swtpm is collapsed into the QEMU identity
- Break: change the `tpm` layout entry from `access: swtpm` to `access: qemu`.
- Red: structural contract — the emulator has a separate runtime identity and
  TPM state must not become readable by the QEMU group by accident.

### 58. A QEMU path loses group traversal
- Break: change `disposable` to `0700` or `access: admin`.
- Red: structural mode/access checks. The hardware run also executes
  `/usr/bin/test -x` as the effective QEMU user.

### 59. The runtime traversal proof is removed
- Break: delete `Verify each non-root runtime identity can traverse its
  directories`.
- Red: structural contract — existence of an account/group does not prove
  supplementary membership or parent traversal.

### 60. A layout override removes a required directory
- Break: delete the runtime assertion against
  `hyperlab_required_directories`.
- Red: refusal `missing-required-directory`.

### 61. A layout stops being a list of mappings
- Break: remove either staged type assertion in `validate.yml`.
- Red: refusals `layout-not-list` or `layout-non-mapping`.

### 62. An unquoted mode reaches later filters
- Break: set a mode to YAML integer `493` or remove the quoted-mode check.
- Red: structural contract and refusal `mode-unquoted-integer`, without a
  traceback.

### 63. Capacity planning becomes a mkdir refusal
- Break: replace the capacity `debug` task with an `assert` on
  `size_available`.
- Red: structural contract. M2 creates empty directories; import is where a
  hard space check belongs.

### 64. The derived capacity plan is lowered
- Break: set `image_store_capacity_plan_gib: 40`.
- Red: structural contract recomputes the minimum from `images/*.yml`.

### 65. A C in the path is mistaken for the NOCOW flag
- Break: parse the full `lsattr` line rather than its first field.
- Red: refusal suite evaluates the real shared NOCOW task with an uppercase C
  only in the pathname.

### 66. NOCOW is applied rather than observed
- Break: replace `/usr/bin/lsattr` with `chattr +C`.
- Red: exact command allowlist and forbidden-operation scan.

### 67. The post-condition stops verifying the resulting layout
- Break: remove any of `stat.pw_name`, `stat.gr_name`, `stat.mode` or `stat.dev`
  from `main.yml`.
- Red: structural contract.

### 68. The store leaves the brick graph
- Break: change `image_store: [kvm_host]` to `image_store: []`.
- Red: both static and image-store structural contracts.

### 69. The scoped playbook pulls in another brick
- Break: add `network_domains` to `playbooks/image-store.yml`.
- Red: structural contract — a directory-layout play must not reconfigure the
  lab bundle.

### 70. Local verification stops discovering brick tests
- Break: remove the `tests/*_contract.py` or `tests/*-refusals.yml` block from
  `verify.sh`.
- Red: `tests/static_contract.py`. This closes the old omission failure where
  the battery could print ALL GREEN without running the new test family.

### 71. Check mode pretends predicted directories already exist
- Break: remove the `when: not ansible_check_mode` guard from the real
  post-condition block or the layout-manifest task.
- Red: `python tests/image_store_contract.py`; on hardware, a first
  `playbooks/image-store.yml --check --diff` against an absent store must finish
  without trying to stat, traverse or copy into directories that check mode did
  not create.

### 72. NOCOW is checked only after the first write
- Break: move `Read NOCOW attribute from the nearest existing store ancestor`
  below `Create each store directory individually`.
- Red: `python tests/image_store_contract.py` — the inheritance source must be a
  pre-write refusal, while the created root is independently verified on the
  real pass.

### 73. The bar execs a helper the role does not deploy
- Break: point any `custom/hyperlab*` `exec` at a path that is not in the
  desktop role's `/usr/local/bin` copy loop.
- Red: the cockpit control invariants - `render_hyper_execs` must be a subset of
  what the role actually installs, or the module silently shows nothing.

### 74. A cockpit module polls faster than 15 seconds
- Break: lower any `interval` on a `custom/hyperlab*` module.
- Red: the minimum interval assertion. Each poll is a process spawn; the signal
  is the fast path, the interval is only the safety net for changes made
  outside the CLI.

### 75. The collapsed pill is no longer the trust level
- Break: reorder `group/hyperlab.modules` so `custom/hyperlab` is not first.
- Red: the drawer's first child is the always-visible one, and trust is the
  single lab fact that cannot be recovered by looking at anything else.

### 76. The CLI and the bar disagree about the refresh signal
- Break: change `WAYBAR_SIGNAL` in `tools/hyperlabctl/hyperlabctl/operations.py`
  without changing `signal` in `waybar.jsonc`.
- Red: the invariant reads the number out of the Python source and compares it
  with the one in the bar config. Drift here is invisible at runtime: the bar
  just stops updating after an action, and nothing errors.

### 77. A cockpit click reaches something other than the palette or the panel
- Break: point an `on-click` at any other command.
- Red: the allowed-clicks difference. The bar is a session surface with no
  password to give, so what it can launch is a closed list.

### 78. The palette runs a privileged action instead of handing it over
- Break: remove the `privileged == yes` branch from
  `privatestack-hyperlab-palette.sh`.
- Red: the palette invariant. That branch is the only thing keeping a sudo
  prompt off a mouse click.

### 79. The checkout pointer lands executable
- Break: set `/etc/hyperlabctl/checkout` to mode `0755`.
- Red: the pointer is data the wrapper reads, not something anyone runs. It is
  asserted 0644 exactly so it cannot drift into the executable class by
  copy-paste from the helper task above it.

### 80. The collapsed cockpit pill goes back to polling
- Break: replace the collapsed module's `exec ... watch` and `restart-interval`
  with a plain `interval`.
- Red: the collapsed module must be a stream. Polling is a process spawn on a
  timer; blocking on `virsh event` costs nothing while nothing happens and
  redraws the instant a domain moves.

### 81. The drawer loses a pill
- Break: remove one entry from `group/hyperlab.modules`.
- Red: the drawer is asserted at exactly three pills behind the collapsed one.
  A silently missing pill looks identical to a pill whose script is failing.

### 82. The CLI wrapper leaves the helper loop
- Break: remove `hyperlabctl-wrapper.sh` from the `/usr/local/bin` copy loop.
- Red: the bar execs `/usr/local/bin/hyperlabctl` through its helper. Without
  the wrapper every pill falls back to "hyperlabctl is not installed", which
  looks exactly like a broken CLI rather than a missing deploy.

### 83. A second copy task installs into /usr/local/bin with the wrong mode
- Break: add any second `ansible.builtin.copy` targeting `/usr/local/bin` with
  a mode other than `0755`.
- Red: the existing rice invariant, which compares the whole list of bin modes
  rather than checking one. This is the reason the new helpers were added to
  the loop that was already there instead of getting a task of their own - a
  second task would have turned that list into `['0755', '0755']` and broken
  CI on push.

### 84. An offered action references a playbook that is not in the checkout
- Break: set any action's `requires` to `None` while its command still names a
  playbook this checkout does not have.
- Red: `tests/hyperlabctl_contract.py`. The palette is generated from the
  registry, so an action that cannot run is an action the operator will pick
  and watch fail.


## Cockpit and M3 integration

These mutations pin the boundary between the desktop role, the shell surface
and the M3 lifecycle. They are cross-file contracts, so
`tests/hyperlabctl_contract.py` or `tests/m3_cockpit_contract.py` is the expected
red check.

### Cockpit command strings regain shell execution
- Break: replace `subprocess.call(argv)` with
  `subprocess.call(" ".join(argv), shell=True)` in
  `roles/desktop/files/privatestack-hyperlab-palette.sh`.
- Red: `tests/hyperlabctl_contract.py`, "the palette executes validated JSON argv".
- Restore: `git checkout -- roles/desktop/files/privatestack-hyperlab-palette.sh`

### Completion executes a mutable checkout as root
- Break: delete `become_user: "{{ admin_user }}"` from the completion task in
  `roles/desktop/tasks/main.yml`.
- Red: `tests/hyperlabctl_contract.py`, "completion runs as the admin user".
- Restore: `git checkout -- roles/desktop/tasks/main.yml`

### Completion becomes a shell command
- Break: replace the completion task's `argv:` block with a `cmd:` string.
- Red: `tests/hyperlabctl_contract.py`, "completion uses argv rather than a shell command".
- Restore: `git checkout -- roles/desktop/tasks/main.yml`

### Managed-domain metadata drifts from the cockpit parser
- Break: change the `xmlns:hyperlab` URI in
  `roles/guest/templates/domain.xml.j2`.
- Red: `tests/m3_cockpit_contract.py`.
- Restore: `git checkout -- roles/guest/templates/domain.xml.j2`

### A managed action bypasses its lifecycle playbook
- Break: point `vm.managed-start` in `tools/hyperlabctl/hyperlabctl/registry.py`
  at `hyperlabctl vm start {domain}` and mark it unprivileged.
- Red: `tests/m3_cockpit_contract.py`.
- Restore: `git checkout -- tools/hyperlabctl/hyperlabctl/registry.py`

### The split QEMU SPICE audio module disappears
- Break: remove `qemu-audio-spice` from `guest_required_packages` in
  `group_vars/all/guest.yml`.
- Red: `tests/static_contract.py` and `tests/contract_mutations.py`. Libvirt
  emits `-audiodev driver=spice` for the managed SPICE display, so Arch's
  separately packaged `audio-spice.so` is a hard runtime dependency.
- Restore: `git checkout -- group_vars/all/guest.yml`

### A managed disk regains libvirt DAC relabel
- Break: remove `<seclabel model="dac" relabel="no"/>` from the primary disk
  source in `roles/guest/templates/domain.xml.j2`.
- Red: `tests/static_contract.py`, `tests/contract_mutations.py` and
  `tests/guest_contract.py`. A disposable start would otherwise let libvirt
  change the sealed backing image from `root:<qemu-group>` to the QEMU user and
  leave it that way after shutdown.
- Restore: `git checkout -- roles/guest/templates/domain.xml.j2`

## Schema and asset contracts

### A domain cube SVG is renamed or deleted
- Break: `mv roles/desktop/files/domain-lab.svg /tmp/`
- Red: `tools/shell-tests/test_design.py`, "every domain icon has its source
  asset", reporting `no source SVG for: lab`. The five-domain block used to
  build a path and discard it, so a missing cube stayed green here and showed
  up only as a broken icon in the running Control Center.
- Restore: `mv /tmp/domain-lab.svg roles/desktop/files/`

### A domain icon path drifts from the deployed location
- Break: change any `icon` value in `DOMAIN_META` inside
  `roles/desktop/files/privatestack-hyperlab-domains.py`.
- Red: `tools/shell-tests/test_design.py`, "every domain icon points at the
  deployed cube path". The desktop role copies to
  `/usr/share/icons/hyperlab/domains/<id>.svg`; the manager must agree.
- Restore: `git checkout -- roles/desktop/files/privatestack-hyperlab-domains.py`

### The VM spec schema stops accepting `auto` memory
- Break: change `memory_mb` from `int_or_auto` to `int` in
  `schemas/vm-spec.v1.yml`.
- Red: `tests/static_contract.py`, "VM spec memory must stay resolvable from
  the live host budget". Every spec ships `memory_mb: auto` so that the host
  budget of ADR 0007 decides; a plain `int` would silently retire that policy.
- Restore: `git checkout -- schemas/vm-spec.v1.yml`

### The VM spec schema gains a third lifecycle or device profile
- Break: add `golden` to the `lifecycle` enum in `schemas/vm-spec.v1.yml`.
- Red: `tests/static_contract.py`, "VM spec schema must enumerate exactly the
  two lifecycles". ADR 0002 and ADR 0009 both depend on the pairs staying
  closed; the schema file was previously parsed but never inspected.
- Restore: `git checkout -- schemas/vm-spec.v1.yml`

## Cross-repository ownership

### The evidence status comes back into the ansible profile
- Break: add `status: component-verified` under any entry of `host_profiles`
  in `group_vars/all/hardware.yml`.
- Red: `tests/static_contract.py`, "must not carry an evidence status", and
  `tests/cross_repo_contract.py` when a sibling checkout is present. ADR 0006
  says a repository cannot certify itself; the field sat there for weeks
  because nothing enforced the decision the ADR had already taken.
- Restore: `git checkout -- group_vars/all/hardware.yml`

### The two repositories disagree on a VFIO ID
- Break: change one ID in `arch-hypervisor-lab/hardware/compatibility.yml`.
- Red: `tests/cross_repo_contract.py`, "VFIO IDs disagree", listing both
  sides. Without a sibling checkout this check skips loudly and says so
  instead of reporting a pass.
- Restore: `git checkout -- hardware/compatibility.yml` in the other repo.

### The dedicated cross-repo job loses its sibling
- Break: run `CROSS_REPO_REQUIRED=1 python tests/cross_repo_contract.py /tmp/absent`.
- Red: the check fails instead of skipping. A single-repo clone may skip; the
  job that exists to compare the pair may not.
