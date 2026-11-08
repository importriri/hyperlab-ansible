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

## roles/host_desktop_sway - the cockpit rice

### 16. Helper deployed 0644
- Break: `sed -i '0,/mode: "0755"/s//mode: "0644"/' roles/host_desktop_sway/tasks/main.yml`
- Red: render suite, "A rice invariant broke" - a config file copied 0644
  is inert, a SCRIPT copied 0644 is a silent no-op: waybar shows an empty
  module and nothing anywhere says why.
- Restore: `git checkout -- roles/host_desktop_sway/tasks/main.yml`

### 17. rofi launcher theme points at a name nobody deploys
- Break: `sed -i 's/@theme "rofi-launcher.rasi"/@theme "launcher.rasi"/' roles/host_desktop_sway/files/rofi-config.rasi`
- Red: `rofi_theme_contract.py` - the launcher must replace the stock theme
  with the exact file deployed by the desktop role. Replacing `@theme` with
  `@import` is also refused because it brought back the light fallback rows
  and broke Mod+D on the Nitro.
- Restore: `git checkout -- roles/host_desktop_sway/files/rofi-config.rasi`

### 17a. rofi selection follows the mouse again
- Break: `sed -i 's/hover-select:        false/hover-select:        true/' roles/host_desktop_sway/files/rofi-config.rasi`
- Red: `rofi_theme_contract.py` - keyboard selection must stay stable instead
  of jumping whenever the pointer crosses a row.
- Restore: `git checkout -- roles/host_desktop_sway/files/rofi-config.rasi`

### 18. Backdrop path drift
- Break: `sed -i 's#backgrounds/privatestack/mocha#backgrounds/mocha#' roles/host_desktop_sway/files/sway.config`
- Red: render suite, "A rice invariant broke" - one wallpaper, three
  files that name it (copy task, sway.config, swaylock.conf). Two out of
  three agreeing is a black desktop or a black lock screen.
- Restore: `git checkout -- roles/host_desktop_sway/files/sway.config`

### 19. cava emits levels the bridge cannot map
- Break: `sed -i 's/ascii_max_range = 7/ascii_max_range = 15/' roles/host_desktop_sway/files/cava-waybar.conf`
- Red: render suite, "A rice invariant broke" - the bridge script maps
  0-7 onto the eighth-block glyphs; raise the range and the extra levels
  reach waybar as bare digits.
- Restore: `git checkout -- roles/host_desktop_sway/files/cava-waybar.conf`

### 20. The old launcher comes back
- Break: `sed -i 's/^  - rofi$/  - rofi\n  - fuzzel/' roles/host_desktop_sway/defaults/main.yml`
- Red: render suite, "A cockpit invariant broke" - one launcher, and it
  is the one the sway binding and the power menu actually call. The same
  assertion refuses `rofi-wayland`: rofi 2.0 Provides/Replaces it, pacman
  resolves that but `pacman -Q` does not, so the module would report
  changed on every run forever.
- Restore: `git checkout -- roles/host_desktop_sway/defaults/main.yml`

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
- Break: `sed -i 's/^for_window \[window_type="dialog"\].*$/for_window [window_type="dialog|menu"]/; /^for_window \[window_type="menu"\]/d' roles/host_desktop_sway/files/sway.config`
- Red: render suite, "A rice invariant broke" - the line above it takes a
  regex (`window_role`), this one does not: sway matches `window_type`
  with `strcasecmp` against a fixed list, an unknown value leaves the
  criteria empty, and sway refuses the whole line at startup with
  "Criteria is empty". Caught on hardware first; this is the check that
  keeps it caught.
- Restore: `git checkout -- roles/host_desktop_sway/files/sway.config`

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

## Optional Acer Nitro platform driver

### 85. Out-of-tree replacement becomes the default
- Break: `sed -i 's/^nitro_sense_out_of_tree_enabled: false$/nitro_sense_out_of_tree_enabled: true/' roles/nitro_sense/defaults/main.yml`
- Red: render suite, "A Nitro Sense invariant broke". A reverse-engineered
  platform driver must never replace a sufficient in-tree driver implicitly.
- Restore: `git checkout -- roles/nitro_sense/defaults/main.yml`

### 86. Generic kernel headers replace hardened headers
- Break: `sed -i 's/^  - linux-hardened-headers$/  - linux-headers/' roles/nitro_sense/defaults/main.yml`
- Red: render suite, "A Nitro Sense invariant broke". Stage 1 boots
  `linux-hardened`; a successful package transaction for another kernel is not
  a build proof for the running host.
- Restore: `git checkout -- roles/nitro_sense/defaults/main.yml`

### 87. Rollback no longer restores acer_wmi
- Break: `sed -i 's/name: "{{ nitro_sense_in_tree_module_name }}"/name: broken_in_tree_driver/' roles/nitro_sense/tasks/rollback.yml`
- Red: render suite, "A Nitro Sense invariant broke". Removing the replacement
  without restoring the in-tree platform driver can leave function keys and
  radio controls unavailable.
- Restore: `git checkout -- roles/nitro_sense/tasks/rollback.yml`

### 88. The Nitro fan path is guessed
- Break: `sed -i 's#/nitro_sense/fan_speed#/nitro_sense/fan_curve#' roles/nitro_sense/defaults/main.yml`
- Red: render suite, "A Nitro Sense invariant broke". Only the exact node
  documented by the pinned upstream source may receive a WMI-backed write.
- Restore: `git checkout -- roles/nitro_sense/defaults/main.yml`

## roles/guest_gpu_nvidia

### 89. The persistent DRM alias becomes a volatile card number
- Break: `sed -i 's#/dev/dri/privatestack-nvidia#/dev/dri/card1#' roles/guest_gpu_nvidia/defaults/main.yml`
- Red: render suite, "A guest NVIDIA invariant broke". DRM card numbers may
  change across boots; Hyprland must consume the udev alias bound to the passed
  display controller's PCI identity.
- Restore: `git checkout -- roles/guest_gpu_nvidia/defaults/main.yml`

### 90. The NVIDIA PCI parser regains YAML-level double escaping
- Break: replace `[.]` with `\\.` and `[ ]+` with `\\s+` in
  `roles/guest_gpu_nvidia/tasks/main.yml`.
- Red: `tests/guest_gpu_nvidia_contract.py`. The test evaluates the pattern
  literals loaded from the role against the Nitro PCI probe and must still
  select only `0000:05:00.0`, never its NVIDIA audio function.
- Restore: `git checkout -- roles/guest_gpu_nvidia/tasks/main.yml`

## roles/guest_looking_glass_linux

### 91. The headless sender asks for an invisible portal selection again
- Break: `sed -i '/custom_picker_binary/d' roles/guest_looking_glass_linux/templates/xdph.conf.j2`
- Red: `tests/looking_glass_linux_contract.py` and the render suite. The
  experimental sender runs on an output that SPICE cannot display, so an
  interactive XDPH picker is a deadlock rather than a useful consent surface.
- Restore: `git checkout -- roles/guest_looking_glass_linux/templates/xdph.conf.j2`


## Cockpit and M3 integration

These mutations pin the boundary between the desktop role, the shell surface
and the M3 lifecycle. They are cross-file contracts, so
`tests/hyperlabctl_contract.py` or `tests/m3_cockpit_contract.py` is the expected
red check.

### Cockpit command strings regain shell execution
- Break: replace `subprocess.call(argv)` with
  `subprocess.call(" ".join(argv), shell=True)` in
  `roles/host_desktop_sway/files/privatestack-hyperlab-palette.sh`.
- Red: `tests/hyperlabctl_contract.py`, "the palette executes validated JSON argv".
- Restore: `git checkout -- roles/host_desktop_sway/files/privatestack-hyperlab-palette.sh`

### Completion executes a mutable checkout as root
- Break: delete `become_user: "{{ admin_user }}"` from the completion task in
  `roles/host_desktop_sway/tasks/main.yml`.
- Red: `tests/hyperlabctl_contract.py`, "completion runs as the admin user".
- Restore: `git checkout -- roles/host_desktop_sway/tasks/main.yml`

### Completion becomes a shell command
- Break: replace the completion task's `argv:` block with a `cmd:` string.
- Red: `tests/hyperlabctl_contract.py`, "completion uses argv rather than a shell command".
- Restore: `git checkout -- roles/host_desktop_sway/tasks/main.yml`

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

### A SPICE domain loses its guest sound device

- Break: delete the `<sound model="ich9">` block from
  `roles/guest/templates/domain.xml.j2`.
- Red: `tests/static_contract.py` and `tests/contract_mutations.py`, "managed
  SPICE domains must expose an ICH9 playback-only sound device".
- Restore: `git checkout -- roles/guest/templates/domain.xml.j2`

### A managed disk regains libvirt DAC relabel
- Break: remove `<seclabel model="dac" relabel="no"/>` from the primary disk
  source in `roles/guest/templates/domain.xml.j2`.
- Red: `tests/static_contract.py`, `tests/contract_mutations.py` and
  `tests/guest_contract.py`. A disposable start would otherwise let libvirt
  change the sealed backing image from `root:<qemu-group>` to the QEMU user and
  leave it that way after shutdown.
- Restore: `git checkout -- roles/guest/templates/domain.xml.j2`

### Runtime guest inventory allocates an SSH pseudo-TTY

- Break: remove `'ansible_ssh_use_tty=false',` from
  `playbooks/vm-guest-inventory.yml`.
- Red: `tests/guest_inventory_contract.py` and
  `tests/contract_mutations.py`, "runtime guest inventory must disable SSH
  pseudo-TTY allocation". Allocating a pseudo-TTY allows terminal-control
  output from the privilege-escalation session to appear after Ansible module
  JSON and corrupt the module protocol boundary.
- Restore: `git checkout -- playbooks/vm-guest-inventory.yml`

## Schema and asset contracts

### A domain cube SVG is renamed or deleted
- Break: `mv roles/host_desktop_sway/files/domain-lab.svg /tmp/`
- Red: `tools/shell-tests/test_design.py`, "every domain icon has its source
  asset", reporting `no source SVG for: lab`. The five-domain block used to
  build a path and discard it, so a missing cube stayed green here and showed
  up only as a broken icon in the running Control Center.
- Restore: `mv /tmp/domain-lab.svg roles/host_desktop_sway/files/`

### A domain icon path drifts from the deployed location
- Break: change any `icon` value in `DOMAIN_META` inside
  `roles/host_desktop_sway/files/privatestack-hyperlab-domains.py`.
- Red: `tools/shell-tests/test_design.py`, "every domain icon points at the
  deployed cube path". The desktop role copies to
  `/usr/share/icons/hyperlab/domains/<id>.svg`; the manager must agree.
- Restore: `git checkout -- roles/host_desktop_sway/files/privatestack-hyperlab-domains.py`

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

### Looking Glass captured-input compatibility patch

- Break: replace the grabbed-aware press gate in
  `roles/looking_glass/files/client-captured-button-press.patch` with the
  upstream `!g_cursor.inView` gate.
- Red: `tests/looking_glass_client_input_contract.py` and
  `tests/contract_mutations.py`. The production client must retain the
  hardware-proven behavior without diagnostic logging, and the build stamp
  must bind the installed binary to the exact reviewed patch bytes.

### Looking Glass KVMFR reload guard

Mutation: remove the runtime-size condition from the KVMFR unload task.

Expected failure: the static contract rejects an unconditional KVMFR unload.
The role must compare the live device size through the versioned ioctl probe,
resolve the module for the running kernel, and refuse live device users before a
real resize.

### Performance/security regression guard

- Break: add `mitigations=off` to the VFIO boot profile in
  `roles/vfio_boot/defaults/main.yml`.
- Red: `tests/performance_security_contract.py` rejects performance settings
  that lower the host security floor.
- Restore: remove the injected token and rerun the contract.

### vfio_boot asks for the mode the ESP keeps

`problems/vfio-boot-modes-on-vfat-esp.md`. Each one turns
`tests/vfio_boot_esp_mode_contract.py` red with the message shown.

- Break: put `mode: "0644"` back on `Install the boot profiles` in
  `roles/vfio_boot/tasks/main.yml`.
  Red: "'Install the boot profiles' writes /boot/loader/entries/{{ item.file }}
  with a fixed mode '0644', not the one the ESP keeps".
- Break: in `tools/esp_file_mode.py`, answer `wanted` on vfat instead of
  `vfat_mode(options)`.
  Red: "the mode decided for the Nitro's ESP (fmask=0022) is not the 0755
  its files read".
- Break: drop the group-or-others write refusal in `decide()`.
  Red: "the tool accepted fmask=0000, which lets everyone write a boot entry".
- Break: drop the dmask refusal in `vfat_mode()`.
  Red: "the tool accepted dmask=0000, which lets everyone create or replace
  a boot entry".
- Break: take dmask as 0022 when the vfat mount does not show one.
  Red: "the tool accepted a vfat mount without dmask".
- Break: remove `vfio_boot_loader_file_mode is string` from the role's
  shape assertion.
  Red: "vfio_boot does not refuse a decided mode that is not a 0NNN string".
- Break: accept any `uid`/`gid` in `vfat_mode()`.
  Red: "the tool accepted a vfat mount whose files belong to uid 1000, not root".
- Break: remove `/boot/loader` from the findmnt loop.
  Red: "vfio_boot does not inspect /boot/loader, where it writes".
- Break: remove `check_mode: false` from the findmnt task.
  Red: "... only reads, but does not run in check mode, so --check --diff
  cannot compare the mode".
- Break: pass only the first findmnt document to the tool
  (`| first` instead of `| list | to_json`).
  Red: "the tool does not read every findmnt document the role collected".
- Restore: `git checkout -- roles/vfio_boot/tasks/main.yml tools/esp_file_mode.py`.

### Execute the ESP decision wiring under Ansible

The entries above preserve the original structural observations. The expanded
`tests/vfio_boot_esp_mode_contract.py` runs the production task objects before
its textual role guards. Runtime observations below were red, then restored
green, using this command from the repository root. Each mutation uses a fresh
disposable copy, backs up its target, invokes the unchanged discovered
entrypoint, restores the saved bytes and repeats all normal/check cases.
No production file in the source checkout is modified.

```bash
python - <<'PY'
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path.cwd()
entrypoint = 'tests/vfio_boot_esp_mode_contract.py'
role = 'roles/vfio_boot/tasks/main.yml'
tool = 'tools/esp_file_mode.py'
files = [entrypoint, role, tool, 'roles/vfio_boot/defaults/main.yml']
mutations = [
    ('stdin-first', role, '| list | to_json', '| first',
     'runtime vfat (normal): unexpected executed tasks'),
    ('fixed-fact', role, '"{{ vfio_boot_esp_mode.stdout }}"', '"0644"',
     'runtime vfat (normal): unexpected task results'),
    ('skip-check-probes', role,
     '  register: vfio_boot_esp_mounts\n  changed_when: false\n  check_mode: false',
     '  register: vfio_boot_esp_mounts\n  changed_when: false',
     'runtime vfat (--check): unexpected executed tasks'),
    ('one-directory', role, '    - /boot/loader\n', '',
     'runtime vfat (normal): findmnt call trace'),
    ('missing-overrides', entrypoint,
     '"--extra-vars", f"@{overrides}", str(play_path)]', 'str(play_path)]',
     'isolated dependency guard failed before commands'),
    ('crashed-refusal', tool, '        return 2\n', '        raise RuntimeError(str(exc))\n',
     'runtime unsafe-dmask (normal): expected deliberate refusal'),
    ('unsafe-selection', role, '  register: vfio_boot_esp_mounts\n',
     '  notify: Unexpected handler\n  register: vfio_boot_esp_mounts\n',
     'unsafe decision task selection'),
    ('changed-probe', role,
     '  register: vfio_boot_esp_mounts\n  changed_when: false\n  check_mode: false',
     '  register: vfio_boot_esp_mounts\n  check_mode: false',
     'runtime vfat (normal): recap changed is not 0'),
    ('duplicate-key', 'roles/vfio_boot/defaults/main.yml',
     'vfio_boot_file_mode: "0644"',
     'vfio_boot_file_mode: "0644"\nvfio_boot_file_mode: "0644"',
     'duplicate YAML keys'),
    ('private-user-site', entrypoint, ' "PYTHONUSERBASE": site.getuserbase(),', '',
     'the runtime child resolves the user site'),
]
mutations = [mutation for mutation in mutations if not sys.argv[1:] or mutation[0] in sys.argv[1:]]
assert mutations
for name, relative, before, after, diagnostic in mutations:
    with tempfile.TemporaryDirectory(prefix='esp-mode-mutation-') as temporary:
        workspace = Path(temporary)
        for relative_source in files:
            destination = workspace / relative_source
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative_source, destination)
        target = workspace / relative
        backup = workspace / 'original'
        shutil.copy2(target, backup)
        original = target.read_text(encoding='utf-8')
        assert original.count(before) == 1, name
        try:
            target.write_text(original.replace(before, after, 1), encoding='utf-8')
            result = subprocess.run([sys.executable, entrypoint], cwd=workspace,
                                    capture_output=True, text=True, timeout=180, check=False)
            print(f'{name}: mutated exit {result.returncode}', flush=True)
            print(result.stdout + result.stderr, flush=True)
            assert result.returncode != 0 and diagnostic in result.stderr, name
            if name == 'skip-check-probes':
                assert 'runtime different-options (normal): deliberate rc=2 refusal' in result.stdout
        finally:
            shutil.copy2(backup, target)
            restored = subprocess.run([sys.executable, entrypoint], cwd=workspace,
                                      capture_output=True, text=True, timeout=180, check=False)
            print(f'{name}: restored exit {restored.returncode}', flush=True)
            print(restored.stdout + restored.stderr, flush=True)
            assert restored.returncode == 0, name
PY
```

| Mutation | Specific observed red check | Restored result |
| --- | --- | --- |
| `stdin-first` | Normal vfat stops at `Decide the file mode the ESP keeps`, tool rc 2, `esp_file_mode: stdin must be a non-empty JSON list`; no publication or success assertion. | Exit 0, all twelve runtime cases and original tool/role checks pass. |
| `fixed-fact` | Normal vfat reaches `Verify the executed ESP mode fact` and fails `vfio_boot_loader_file_mode == '0755'`; the source shape assertion alone accepts the wrong string `0644`. | Exit 0, vfat publishes string `0755` in both modes. |
| `skip-check-probes` | All six normal cases pass as the positive control. Check-mode vfat skips the real probe task, then the decision task returns rc 2, `esp_file_mode: a findmnt document is not valid JSON: Expecting value: line 1 column 1 (char 0)`. | Exit 0, both probes execute in normal and check mode. |
| `one-directory` | Normal vfat finishes its fact assertion, but the trace has only `['-J', '-T', '/boot/loader/entries', '-o', 'TARGET,FSTYPE,OPTIONS']`, missing the `/boot/loader` call. | Exit 0, exactly both reviewed argv calls in every case. |
| `missing-overrides` | The initial `Verify isolated ESP fixture dependencies` assertion fails on the repository root before either command runs. | Exit 0, effective paths point to the temporary fake and the real repository tool. |
| `crashed-refusal` | `runtime unsafe-dmask (normal): expected deliberate refusal` rejects tool rc 1 and its traceback at the decision task, even though Ansible itself exits 2. | Exit 0, deliberate tool rc 2 and exact diagnostic in both modes. |
| `unsafe-selection` | `unsafe decision task selection` refuses the added `notify` before executing Ansible. | Exit 0, only the four reviewed task objects are selected. |
| `changed-probe` | Removing the probe's `changed_when: false` completes the fact assertion but fails `runtime vfat (normal): recap changed is not 0`, with actual changed=1. | Exit 0, changed=0 in every normal/check case. |
| `duplicate-key` | Repeating the default mode key fails `duplicate YAML keys` before executing Ansible. | Exit 0, the unambiguous real defaults load successfully. |
| `private-user-site` | Dropping `PYTHONUSERBASE` from the child environment fails `the runtime child resolves the user site` before any play runs: with HOME private, the child's user site moves under the temporary directory, where a `pip install --user` ansible (as in CI) cannot be imported. | Exit 0, the child resolves the parent's user site. |

Every restored invocation also checks ext4 default string `0644`, ext4 custom
string `0600`, unsafe `dmask=0000`, different targets and different options,
in both modes. Successful cases have zero changes and six OK tasks (fixture
path guard, four production tasks, expected-fact assertion); deliberate
refusals have two OK tasks and one failed decision, no skipped, unreachable,
rescued or ignored tasks. The standalone tool's original refusal helper and
cases remain unchanged; the stricter rc/diagnostic proof applies to the new
Ansible refusal scenarios.

### The sender-identity contract depends on the local zone

`problems/acceptance-contract-depended-on-the-local-zone.md`.

- Break: in `check_sender_identity()` of
  `tests/acceptance_scripts_contract.py`, set
  `since = time.mktime(time.strptime("2026-10-06 22:30:00", "%Y-%m-%d %H:%M:%S"))`.
- Red: `tests/acceptance_scripts_contract.py`, "a sender of this build was
  refused (TZ=UTC0)", in any zone the contract itself runs in.
- Break: remove the `time.tzset()` inside the zone loop (not the one in
  `finally`).
  Red: "TZ=<zone> is not in effect", for the first zone that is not the
  machine's own (observed: "TZ=UTC0 is not in effect: +0200, not +0000").
- Restore: `git checkout -- tests/acceptance_scripts_contract.py`.

### Sender start lines need an explicit UTC offset

`problems/acceptance-contract-depended-on-the-local-zone.md`, follow-up.

Observed in temporary copies of `tools/acceptance/sender_identity.py`, with
unchanged copies of its two expected-pin YAML files. Before each break,
the source was saved with `shutil.copyfile(source, backup)`; restoration
used `shutil.copyfile(backup, target)`. The loaded contract's `DIR` pointed
only at that temporary fixture. No production test override was added.

The checks were `check_sender_identity_timestamps()` and
`check_sender_identity_cli()` from `tests/acceptance_scripts_contract.py`,
with `TZ` and `time.tzset()` set to each existing `SENDER_ZONES` entry and
the effective offset checked. Each of the following turned red in all
four zones, then green after restoring the saved bytes (including all 88
CLI cases through file and standard input):

| Break in the temporary judge | Observed red |
| --- | --- |
| Replace the parse/offset-guard/conversion block with `when = datetime.fromisoformat(started).timestamp()` | `timezone-free start: expected timestamp verdict False`; CLI incorrectly exits 0. |
| Replace the guard's `raise ValueError(...)` with `started_at = started_at.replace(tzinfo=timezone.utc)` and import `timezone` | The same timezone-free refusal fails; CLI incorrectly exits 0. |
| Replace `when = started_at.timestamp()` with `when = started_at.replace(tzinfo=timezone.utc).timestamp()` and import `timezone` | `negative offset: expected timestamp verdict True`; CLI incorrectly exits 1. |
| Replace `when >= since` with `when > since` | `inclusive boundary: expected timestamp verdict True`; CLI incorrectly exits 1. |
| Replace `when >= since` with `True` | `one second stale: expected timestamp verdict False`; CLI incorrectly exits 0. |
| Replace `except ValueError:` with `except TypeError:` (CLI check) | Exit 1 with a traceback fails `the CLI did not return ordinary findings`. |

Before the fix, `TZ=UTC0 python tests/acceptance_scripts_contract.py` also
failed on `timezone-free start` in the normal discovered zone loop. After
the fix it printed `Acceptance scripts contract: OK`.

### The showcase script keeps host values off the take

`problems/showcase-demo-showed-host-values-on-camera.md` and
`problems/showcase-name-pattern-checked-three-characters.md`. Each break
goes into `tools/showcase/demo.sh` and turns `tests/showcase_contract.py`
red with the message shown. The fixture's stubs and environment carry the
sentinel `zq7x` and the address `203.0.113.77`.

- Break: put the old block back after the generic checklist (host name
  from `/proc/sys/kernel/hostname`, `id -un`, `${HOME}`, `ip -4 -o addr`),
  or any one of its four prints alone.
  Red: "walkthrough: a private sentinel (zq7x) reached stdout" (for the
  address print alone: "(203.0.113.77) reached stdout").
- Break: print `${HOME}` or `$(id -un)` with `>&2`.
  Red: "walkthrough: a private sentinel (zq7x) reached stderr".
- Break: read the host name with the `read` builtin from
  `/proc/sys/kernel/hostname` and print it. No stub can answer a builtin.
  Red: "the showcase script reads a host file: /proc/" (the source check,
  not the fixture).
- Break: drop `2>&1` from `shell_ipc` or from the preflight `qs` call,
  drop `2>/dev/null` from the inventory call, or drop `2>&1` from
  `open looking-glass`.
  Red: "walkthrough: a private sentinel (zq7x) reached stderr".
- Break: drop `2>/dev/null` after the inventory parser.
  Red: "unreadable inventory: stderr is not the one reason 'the Machine
  inventory is not readable'" (the traceback carries no sentinel; the
  one-line rule catches it).
- Break: remove the `*[!a-z0-9-]*` refusal.
  Red: "name ['x;id']: exit status 1, not 2".
- Break: remove the 31-character limit.
  Red: "name ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']: exit status 1, not 2".
- Break: read an unreadable preflight inventory as absent
  (`|| state=absent`).
  Red: "failed inventory: the take went on".
- Break: remove the `already exists` refusal.
  Red: "duplicate Machine: exit status 0, not 1".
- Break: remove the 900-second bound of `wait_running`.
  Red: "Machine never running: stderr is not the one reason 'demo-01 is
  not running after 15 minutes'" (the fixture's `sleep` gives up after
  1000 seconds).
- Break: drop `>/dev/null 2>&1` from `sleep 5` (the fixture's `sleep`
  answers with sentinels on both streams).
  Red: "walkthrough: a private sentinel (zq7x) reached stdout".
- Break: drop the `|| { ...; fail ...; }` after `sleep 5`.
  Red: "sleep failing during the wait: stderr is not the one reason 'the
  wait for demo-01 was interrupted'".
- Break: drop `sleep` from the preflight tool loop.
  Red: "without sleep: stderr is not the one reason 'sleep is not
  installed'".
- Break: delete the `wait "${viewer}" ... || fail` line of
  `check_looking_glass`.
  Red: "Looking Glass failing during shot 5: exit status 0, not 1".
- Break: delete the `check_looking_glass` before the last `shell_ipc`.
  Red: "Looking Glass failing during shot 6: exit status 0, not 1".
- Break: delete the `kill -0` test, so the script waits for the client.
  Red: "Looking Glass failing during shot 6: the script did not finish
  within 120 seconds" (that stub ends only at shot 6's prompt; the case
  takes the full 120 seconds). The lingering-client case alone is red too:
  "Looking Glass client still running: the script waited for the client to
  end" (its stub sleeps 20 seconds).
- Break: print `${PWD}` before shot 1, or `$0` on stderr. The fixture runs
  the script by its full path from a checkout inside the sentinel home.
  Red: "walkthrough: a private sentinel (zq7x) reached stdout" (stderr
  for `$0`).
- Break: add `sudo -n true` before shot 1.
  Red: "walkthrough: the script ran a privileged or lifecycle tool:
  [['sudo', '-n', 'true']]".
- Break: add `hyperlabctl machine delete "${name}"` before the last
  `shell_ipc`.
  Red: "walkthrough: hyperlabctl was asked for ['machine', 'delete',
  'demo-01']".
- Restore: `git checkout -- tools/showcase/demo.sh`.

### The showcase fixture tells an exited client from a reaped one

`problems/showcase-contract-waited-for-reaping.md`. Each break goes into
`exited()` or `client_pid()` in `tests/showcase_contract.py` and turns
`python tests/showcase_contract.py` red with the message shown before the
take runs, whatever `sh` is. To replay the Looking Glass breaks above
under dash, put a directory whose `sh` links to dash first in `PATH`;
they are red under dash as under Bash.

- Break: replace the body of `exited()` with
  `return not Path(f"/proc/{pid}").exists()` (the check CI timed out on
  under dash).
  Red: "exit predicate: an exited, unreaped child counts as running".
- Break: replace the body of `exited()` with `return True`.
  Red: "exit predicate: a live child counts as exited".
- Break: drop the `require` on `<proc>/self/stat`, so a missing proc
  filesystem reads as every process gone.
  Red: "exit predicate: a missing proc filesystem counts as an exit".
- Break: in `client_pid()`, return `None` instead of refusing a line that
  is not a PID.
  Red: "client PID: '\n' was not refused".
- Break: in `client_pid()`, accept a file without its newline
  (`if not text:` for `if not text.endswith("\n"):`).
  Red: "... open-pid does not hold a PID: '12'".
- Break: put the first parser back in `exited()`, which split the line at
  its last `") "` and read the next word as the state.
  Red: "exit predicate: '7) Z\n' was not refused".
- Break: in `STAT_LINE`, accept any number of fields after the state
  (`(?: -?[0-9]+)*` for `(?: -?[0-9]+){49,}`).
  Red: "exit predicate: '7 (sh) Z\n' was not refused".
- Break: in `STAT_LINE`, accept a line with fewer than 49 fields after the
  state (`{1,}` for `{49,}`).
  Red: "exit predicate: '7 (sh) Z 1 -20 0 ... 0\n' was not refused" (48
  numbers).
- Break: in `STAT_LINE`, make the opening parenthesis optional (`\(?` for
  `\(`).
  Red: "exit predicate: '7 sh) Z 1 -20 0 ... 0\n' was not refused".
- Break: in `client_pid()`, read the file a second time for the result
  (`return int(path.read_text())`).
  Red: "client PID: '12\n' was read 2 times, not once".
- Restore: `git checkout -- tests/showcase_contract.py`.

Permission-denied read regression (observed on a disposable copy of
`tests/showcase_contract.py`, with unchanged copies of `tools/showcase/demo.sh`,
`docs/showcase.md` and
`roles/host_desktop_common/files/quickshell/hyperlab/ShellIpc.qml`):

- Break: change only `except (FileNotFoundError, ProcessLookupError):` to
  `except (FileNotFoundError, ProcessLookupError, PermissionError):` in
  `exited()` (insert the 17 bytes `, PermissionError`). Run
  `python tests/showcase_contract.py` from the disposable fixture root.
  Before this regression, that mutation stayed green: exit 0,
  "Showcase contract: OK"; the directory-read refusal did not catch it.
  With the regression, red (exit 1): "exit predicate: a denied stat read
  returned True instead of propagating PermissionError". The real
  `self/stat` file was present and the double had recorded exactly the
  intended PID stat read before that assertion failed. The new case
  requires the injected exception itself, rather than any refusal or a
  boolean result, and the double is passed only to that call.
- Restore: copy the saved intact contract over the disposable fixture's
  `tests/showcase_contract.py`, confirm the bytes with `cmp`, then rerun
  `python tests/showcase_contract.py`: green (exit 0), "Showcase contract:
  OK". The whole contract passes, including missing-PID, directory-read,
  malformed-line, live/zombie/reaped, single-read PID and walkthrough
  controls. The working predicate and production files were never changed.

### The showcase take keeps the chosen Machine

`tests/showcase_contract.py` completes the take twice: for `demo-01`
beside an unrelated running `other-01`, and for `v1-showcase` beside an
unrelated `demo-01` that is already running while `v1-showcase` goes from
absent to creating to running. Each break goes into
`tools/showcase/demo.sh` of a throwaway copy of the files the contract
reads (`tests/showcase_contract.py`, `tools/showcase/demo.sh`,
`docs/showcase.md` and `ShellIpc.qml`, at their repository paths); run
the copy's `tests/showcase_contract.py`. Every break below passes the
`demo-01` take and the contract as it was before the second take.

- Break: add `name=demo-01` after the 31-character limit.
  Red: "walkthrough v1-showcase: shot 2 does not give the chosen Machine
  name v1-showcase", followed by the script's own refusal "demo: demo-01
  already exists; pick a new name for a clean take".
- Break: open `demo-01` instead of `"${name}"` in the `open looking-glass`
  line.
  Red: "walkthrough v1-showcase: hyperlabctl was asked for ['open',
  'looking-glass', 'demo-01']" (every shot completes).
- Break: give `name demo-01,` instead of `name ${name},` in shot 2.
  Red: "walkthrough v1-showcase: shot 2 does not give the chosen Machine
  name v1-showcase".
- Break: in `wait_running`, ask `state_of demo-01` instead of
  `state_of "$1"`.
  Red: "walkthrough v1-showcase: shot 3 did not wait for the inventory to
  show v1-showcase running" (the wait ends on the unrelated running
  Machine at once, without a sleep).
- Restore: copy the intact `demo.sh` back; the copy's contract prints
  "Showcase contract: OK".

### A release gate passes only with every reviewed boolean true

`problems/release-pass-with-false-booleans.md`. The breaks go into
`tools/release_acceptance.py` (M1-M7) or `tools/release_probe.py`
(M8-M9). Run `python tests/release_acceptance_contract.py` and
`python tests/release_probe_contract.py`; they build temporary fixture
campaigns only. The red message is the first one each contract prints.

- M1. Break: in `validate_gate_payload`, replace
  `value is True or not complete,` with `True,`.
  Red: acceptance contract, "repository-software.clean_worktrees=false
  was recorded as a pass" (record) and "status accepted an edited pass
  with repository-software.clean_worktrees=false" (status and seal).
- M2. Break: delete `"spice_socket_private",` from `BOOL_FIELDS`.
  Red: acceptance contract, "tool booleans differ from the reviewed
  manifest booleans: missing=['spice_socket_private'] extra=[]", "pass
  gate looking-glass accepted spice_socket_private='true'" and the record
  and edited-evidence cases for `looking-glass`; probe contract, "field
  spice_socket_private is not a reviewed boolean".
- M3. Break: check truth only on record. Replace
  `value is True or not complete,` with `True,` and, after
  `validate_gate_payload(planned, payload, ...)` in `record_gate`, add a
  loop over `BOOL_FIELDS & set(payload)` that requires `payload[field] is
  True or status_value != "pass"`.
  Red: "status accepted an edited pass with
  repository-software.clean_worktrees=false". The record case stays
  green, as it should: `record_gate` still checks the incoming payload
  itself. Only the read paths lose the guard, which is what this break
  is meant to show.
- M4. Break: `isinstance(value, bool),` becomes
  `isinstance(value, (bool, int, str)),`.
  Red: "pass clean_worktrees='true': passed evidence gate
  repository-software field clean_worktrees must be true" (the refusal
  names truth instead of the type); in a failed gate the text is
  accepted.
- M5. Break: `"ready_to_seal": True,` in `status_report`.
  Red: "a pending campaign is ready to seal" and "a campaign failed at
  repository-software is ready to seal".
- M6. Break: `value is True or not complete,` becomes `value is True,`.
  Red: "a failed gate cannot hold repository-software.clean_worktrees=false"
  and "repository-software.clean_worktrees=false refused in a failed gate".
- M7. Break: add `"loopback_spice",` back to `BOOL_FIELDS`.
  Red: "tool booleans differ from the reviewed manifest booleans:
  missing=[] extra=['loopback_spice']"; probe contract, "gate looking-glass
  fields differ: missing=[] extra=['loopback_spice']".
- M8. Break: in `build_payload`, delete the `require(field not in
  BOOL_FIELDS, ...)` line of the `--value` loop.
  Red: probe contract, "boolean text was accepted", "boolean field
  clean_worktrees needs --true or --false" and "--value
  spice_socket_private=true was accepted".
- M9. Break: in the `--false` loop of `build_payload`,
  `set_once(field, False)` becomes `set_once(field, True)`.
  Red: probe contract, "--false clean_worktrees did not give false".
- Restore: `git checkout -- tools/release_acceptance.py tools/release_probe.py`.

### The creation plan agrees with the factory; a refused creation keeps nothing

`problems/machine-create-kept-record-after-projection-refused.md`. Each one
turns the named contract red with the message shown.

- Break: in `creation_plan()` of
  `tools/hyperlabctl/hyperlabctl/machine_provision.py`, set
  `profiles[profile] = {"memory_mb": "auto", "vcpus": 4, "disk_gib": 20}`
  instead of calling `_resource_values`.
  Red: `tests/c10_machine_create_plan_contract.py`, "workstation-dev/balanced:
  the plan differs from the record create writes".
- Break: in `_resource_values()` of `machine_factory.py`, compare a custom
  memory request with `MEMORY_FLOOR_MB` instead of
  `custom_limits(image)["memory_mb_min"]`.
  Red: `tests/c10_machine_create_plan_contract.py`, "server-arch: the
  factory accepted memory_mb=2047, below the plan's limit".
- Break: in `create()` of
  `roles/host_desktop_common/files/privatestack-machine-actions.py`, drop
  `command.append("--project")` and call `machine project NAME` after the
  creation, as two calls.
  Red: `tests/c10_machine_create_plan_contract.py`, "a refused projection
  left a record on a fresh registry: ['.lock', 'srv-01.yml']";
  `tests/host_machine_actions_bridge_contract.py`, "an unconfirmed creation
  went on: {} -> 'crashed: ... unexpected hyperlabctl call ('machine',
  'project', 'srv-a')'".
- Break: in `_undo_creation()` of `commands/machine.py`, replace the call
  to `_remove_staged_spec()` with `reason = None`.
  Red: `tests/c10_machine_create_plan_contract.py`, "['link']: a creation
  refused with no record left a record or spec behind".
- Break: in `MachineCommand._create()`, pass `None` instead of the
  announced publication to `_undo_creation()`, so the record the real
  `os.link` published is not undone.
  Red: `tests/c10_machine_create_plan_contract.py`, "['fsync']: a creation
  refused with the record published left a record or spec behind".
- Break: in `create_machine()` of `machine_registry.py`, replace the call
  to `withdraw_published()` with `left = None`.
  Red: `tests/c10_machine_registry_contract.py`, "a creation refused after
  its publication left its record behind". (The create-plan contract stays
  green: the CLI calls `publish_machine()`, not `create_machine()`.)
- Break: in `_undo_creation()`, change `if left:` before "is kept, since
  the record's withdrawal did not complete" to `if False:`, so the spec is
  removed although the record stays.
  Red: `tests/c10_machine_create_plan_contract.py`, "['fsync',
  'unlink-record']: the spec was removed".
- Break: in `withdraw_published()`, replace the regular-file and inode
  condition with `False`.
  Red: `tests/c10_machine_create_plan_contract.py`, "['fsync',
  'copy-record']: an unfinished undo was not reported as such".
- Break: in `withdraw_published()`, append `and False` to the digest
  comparison.
  Red: `tests/c10_machine_create_plan_contract.py`, "['fsync',
  'rewrite-record']: an unfinished undo was not reported as such".
- Break: in `_remove_staged_spec()`, append `and False` to
  `_identify(path) != staged`.
  Red: `tests/c10_machine_create_plan_contract.py`, "['fsync',
  'replace-spec']: an unfinished undo was not reported as such".
- Break: in `MachineCommand._create()`, replace
  `with registry_lock(create=True):` with `with contextlib.nullcontext():`.
  Red: `tests/c10_machine_create_plan_contract.py`, "['link']: a removal
  ran without the registry lock"; with `check_withdraw` run on its own,
  "a staged creation did not wait for the registry lock".
- Break: in the bridge's `create()`, drop the comparison of the answer's
  `spec` with `vm-specs/.generated/NAME.yml`.
  Red: `tests/host_machine_actions_bridge_contract.py`, "an unconfirmed
  creation went on".
- Break: let the bridge's `TOKEN` start with a dash
  (`^[a-z0-9-][a-z0-9-]{0,63}$`).
  Red: `tests/host_machine_actions_bridge_contract.py`, "an option-like value
  at position 4 reached hyperlabctl".
- Break: drop the early `NUMBER` check in the bridge's `create()`, so the
  custom values are checked only after the plan is read.
  Red: `tests/host_machine_actions_bridge_contract.py`, "an option-like value
  at position 7 reached hyperlabctl".
- Break: in `guest_key()` of `machine_provision.py`, let the type check
  pass `ssh-rsa` (`if kind not in ("ssh-ed25519", "ssh-rsa"):`).
  Red: `tests/c10_machine_create_plan_contract.py`, "rsa key refused for
  the wrong reason" (the shape check still refuses it, without naming the
  type).
- Break: in `guest_key()`, count only the non-blank lines again
  (`[line for line in text.splitlines() if line.strip()]`).
  Red: `tests/c10_machine_create_plan_contract.py`, "leading blank key
  accepted".
- Break: in `withdraw_machine()` of `machine_registry.py`, skip the digest
  comparison.
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw with digest
  '000...000': 0".
- Break: in `MachineCommand._withdraw()`, compare the generated spec with
  the projection by `is` instead of `==`.
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw removed a
  projected Machine".
- Break: in `MachineCommand._withdraw()`, remove the `domain_names(ctx)`
  check.
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw removed a
  record whose domain exists".
- Break: in `MachineCommand._withdraw()`, replace `with registry_lock():`
  with `with contextlib.nullcontext():` (and import `contextlib`).
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw did not wait
  for the registry lock".
- Break: the same in `MachineCommand._project()`.
  Red: `tests/c10_machine_create_plan_contract.py`, "project did not wait
  for the registry lock".
- Break: in `guest_key()` of `machine_provision.py`, return
  `"fingerprint": "SHA256:wrong"`.
  Red: `tests/c10_machine_creation_plan_contract.py`, "guest key not
  reported"; `tests/c10_machine_create_plan_contract.py`, "a valid guest
  key was not accepted". Both compute the expected fingerprint of their
  synthetic key themselves.
- Break: in `MachineCommand._withdraw()`, catch `ContractError` from
  `read_generated_spec()` and set `existing = None`.
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw went on with
  a malformed spec: 0".
- Break: in `read_generated_spec()` of `machine_factory.py`, load with
  `yaml.SafeLoader` instead of `_UniqueKeyLoader`.
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw went on with
  a duplicate key spec: 0".
- Break: in `MachineCommand._create()`, catch `Exception` instead of
  `BaseException` around the publication.
  Red: `tests/c10_machine_create_plan_contract.py`,
  "['interrupt-after-link']: a creation refused with the record published
  left a record or spec behind (record kept: True, spec kept: True)".
- Break: the same in `create_machine()` of `machine_registry.py`.
  Red: `tests/c10_machine_registry_contract.py`, "a cancellation after the
  publication escaped create_machine(); record left: True".
- Break: in `publish_machine()`, delete the `announce(publication)` call
  before `os.link`, so the caller learns of the publication only once it
  returns.
  Red: `tests/c10_machine_create_plan_contract.py`, "['fsync']: a creation
  refused with the record published left a record or spec behind (record
  kept: True, spec kept: False)"; `tests/c10_machine_registry_contract.py`,
  "a creation refused after its publication left its record behind".
- Break: in `create_machine()`, replace `with registry_lock(...)` with
  `with contextlib.nullcontext():`.
  Red: `tests/c10_machine_registry_contract.py`, "a library rollback
  removed a record without the registry lock"; with
  `verify_library_creation_locked` run on its own, "create_machine()
  published while another process held the registry lock".
- Break: in `read_generated_spec()` of `machine_factory.py`, replace
  `if not stat.S_ISDIR(info.st_mode):` with `if False:`.
  Red: `tests/c10_machine_create_plan_contract.py`, "withdraw went on
  through a dangling generated directory link".
- Break: in `MachineCommand._create()`, replace
  `if digest != published.sha256:` with `if False:`.
  Red: `tests/c10_machine_create_plan_contract.py`, "['wrong-digest']: a
  creation refused with the record published left a record or spec behind
  (record kept: True, spec kept: True): launched".
- Restore: copy the broken file back from the copy taken before the break.

### Public content stays free of process wording and a local login

`tests/public_repository_process_hygiene_contract.py` and a local
assertion playbook. The breaks were made in a temporary copy of the
tree: the files of `git ls-files -c -o --exclude-standard` copied to a
new directory, which then gets `git init`, so the contract discovers
every file there as untracked. The playbook runs from that copy with
`-i inventory.ini` on `localhost` through the local connection, gathers
no facts and asserts `hostvars['svc-jellyfin']['ansible_user']` equals
the expected name and `admin_user`; it never contacts the service VM.
It runs three times: with the repository setting, and with
`-e admin_user=svcproofa` and `-e admin_user=svcproofb` (the positive
controls, green on the intact tree). `ansible-inventory --host
svc-jellyfin` shows only the unrendered `{{ admin_user }}`, which is
why the value is asserted in a play. The red message is the one the
contract prints.

The playbook observes one host variable, `ansible_user`, after
rendering; "effective user" in the entries below means that value. It is
not the SSH login. The SSH connection plugin reads its `remote_user`
option from the variables `ansible_user` and `ansible_ssh_user`, in that
order, and when both are set the later one in that list,
`ansible_ssh_user`, is chosen. The playbook never asks the plugin, so it
cannot see a competing alias. For M7 the choice was resolved separately,
with the installed Ansible 2.21.4 and no connection: in a temporary copy
made the same way, `PlaybookCLI` parsed `-i inventory.ini` and the `-e`
overrides and built the inventory and variables. A play for
`svc-jellyfin` and a task that never ran gave the task variables. The
`ssh` plugin, chosen by the task's connection keyword, was loaded but
never connected. It received the rendered variables through
`_resolve_option_variables` and `set_options`, as the task executor
passes them, and `get_option_and_origin('remote_user')` returned the
login and its source. Process spawns and socket connects were trapped
during resolution and none happened. On the intact inventory it returned
`svcproofa` and `svcproofb` for the two overrides and the configured
`admin_user` without one, each from `var: ansible_user`.

- M1. Break: put "outside the restricted" and, on the next line, the
  removed two-word phrase back at the end of the introductory note of
  `docs/c9-independent-review-2026-09-27.md`.
  Red: "FAIL public process metadata:
  docs/c9-independent-review-2026-09-27.md:11". The playbook stays
  green: it does not read the document.
- M2. Break: the `svc-jellyfin` line of `inventory.ini` gets back the
  literal `ansible_user=` of the configured name.
  Red: "FAIL public connection identity: inventory.ini:5: connection
  user is not the admin_user setting"; playbook red for both overrides
  (the effective user stays the literal).
- M3. Break: `ansible_user=svcliteral`, an unrelated synthetic name.
  Red: the same contract message; playbook red in all three runs.
- M4. Break: delete `ansible_user="{{ admin_user }}"` from the line.
  Red: "inventory.ini:5: svc-jellyfin sets its connection user 0
  times"; playbook red in all three runs (no `ansible_user`).
- M5. Break: `ansible_user="{{ 'NAME' }}"`, a quoted constant.
  Red: "inventory.ini:5: connection user does not parse". The INI
  plugin evaluates that value as a set inside a set and rejects the
  whole inventory, so the playbook is red in all three runs. Before the
  contract caught `TypeError` here it stopped with a traceback.
- M5b. Break: `ansible_user="{{ 'NAME' | string }}"`, a constant the
  plugin accepts.
  Red: "connection user is not the admin_user setting"; playbook red
  for both overrides.
- M6. Break: `ansible_user="{{ guest_cloud_init_user }}"`.
  Red: the same contract message; playbook red for both overrides.
- M7. Break: a `[services:vars]` section with
  `ansible_ssh_user=svcliteral` before `[jellyfin]`.
  Red: "inventory.ini:8: connection user is not the admin_user
  setting". The playbook stays green in all three runs because the
  rendered `ansible_user` is unchanged; it does not show the SSH login.
  The SSH plugin's resolution picks the group alias: `svcliteral` from
  `var: ansible_ssh_user`, with `-e admin_user=svcproofa` and in the
  other two runs. Only the contract catches M7. With the injected alias
  removed, the contract is green, the playbook is green three times and
  the resolution is `svcproofa` and `svcproofb` again.
- M8. Break: uncomment the `devbox` line and add
  `ansible_user=svcliteral`.
  Red: "inventory.ini:13: connection user is not the admin_user
  setting". Playbook green, as it reads only `svc-jellyfin`.
- M9. Break: a second identical `svc-jellyfin` line in `[services]`.
  Red: "inventory.ini:0: svc-jellyfin is defined 2 times in
  [services]". Playbook green.
- M10. Break: append a second `ansible_user="{{ admin_user }}"` to the
  line.
  Red: "inventory.ini:5: svc-jellyfin sets its connection user 2
  times". Playbook green: both assignments carry the same value.
- M11. Break: move `inventory.ini` away.
  Red: "inventory.ini:0: inventory is unreadable"; playbook red in all
  three runs.
- M12. Break: append `[extra:children]`, then `[jellyfin] # connection
  identity` and `svc-jellyfin ansible_user=svcliteral`.
  Red: "inventory.ini:16: connection user is not the admin_user
  setting"; playbook red in all three runs (the later line wins, the
  effective user is the literal). Before the contract took the plugin's
  section expression, which allows a trailing `#` comment, it read the
  commented header as a line of `[extra:children]`, skipped the host
  line after it and stayed green.
- M13. Positive control: `[services]` becomes `[services] # service
  VMs`. Contract and playbook stay green. Before the same fix the
  contract refused it with "svc-jellyfin is defined 0 times in
  [services]".
- M14. Break: append `[extra:children]` and
  `svc-jellyfin ansible_user=svcliteral`.
  Red: "inventory.ini:15: child group line does not parse". The plugin
  refuses the inventory with "Expected group name"; the playbook stays
  green only because the hosts read before that line remain loaded.
- M15. Break: `[jellyfin]` becomes `[jellyfin] ; connection identity`
  (the plugin's header comment is `#` only).
  Red: "inventory.ini:7: host variable is not key=value" and
  "svc-jellyfin is defined 2 times in [services]". Playbook green.
- M16. Break: append `[jellyfin:hostz]` and
  `svc-jellyfin ansible_user=svcliteral`.
  Red: "inventory.ini:14: section type is unknown" and "inventory.ini:15:
  connection user is not the admin_user setting". Playbook green for the
  same reason as M14: the plugin refuses the inventory with "Section
  [jellyfin:hostz] has unknown type: hostz" after the hosts above it.
- Restore: copy the broken file back from the intact tree; the contract
  prints "Public repository process hygiene contract: OK" and the three
  playbook runs pass again.

### Machine provisioning runs the reviewed plan on the exact projection

`tests/host_machine_provision_contract.py`,
`tests/c10_machine_creation_plan_contract.py`,
`tests/host_operation_lifecycle_contract.py` and
`tests/host_operation_integration_contract.py`. Each break was made in
the working tree with a copy of the file kept aside, the named contract
run (`python tests/<contract>.py`), the copy put back and the contract
run again green. The red message is the one the contract prints.

- M1. Break: in `resolve()` of `privatestack-operation.py`, accept any
  argv whose first element is the provisioner (`argv[:1] ==
  [PROVISION]`).
  Red (lifecycle): "the runner accepted a provisioning command with
  extra argument".
- M2. Break: accept any two-element argv starting with the provisioner,
  whatever the name.
  Red (lifecycle): "the runner accepted a provisioning command with
  another Machine".
- M3. Break: the registry's `machine.provision` command back to
  `privatestack-machine-provision --spec {spec} {domain}` (absolute).
  Red (lifecycle): the first `resolve()` raises
  "invalid-reviewed-command".
- M4. Break: in `provision_steps()`, `if not same_document(stored,
  project_vm_spec(root, record)):` becomes `if False:`.
  Red (creation plan): "projection case memory: accepted what must be
  refused (differs from the projection)"; red (provisioner, real CLI):
  "the provisioner ran with an edited spec (memory)", three playbooks
  called.
- M5. Break: drop `and spec_hash == record["spec_digest"]` from the
  run-time check in `run()`.
  Red (lifecycle): "drifted spec ran", the child the runner tried to
  start after the spec changed.
- M6. Break: check the playbook files in the step loop of `main()`
  instead of in `steps_for()`.
  Red (provisioner): "a plan with a missing final playbook ran or
  asked", four playbooks called and the password asked before the
  refusal.
- M7. Break: check every playbook file but the last
  (`for step in steps[:-1]:`).
  Red (provisioner): "a plan with a missing final playbook ran or
  asked", all five called.
- M8. Break: `CANCELLING = (signal.SIGHUP,)`, no SIGTERM handler.
  Red (provisioner, real PTY): "the hash file outlived SIGTERM".
- M9. Break: `CANCELLING = (signal.SIGTERM,)`, no SIGHUP handler.
  Red (provisioner, real PTY): "the hash file outlived SIGHUP".
- M10. Break: `provision_steps()` no longer appends `profile-second`.
  Red (creation plan): "steps: ['create-domain', 'inventory',
  'profile-first', 'close-access']".
- M11. Break: `provision_steps()` no longer appends `close-access`.
  Red (creation plan): "server steps differ from docs/first-machine.md".
- M12. Break: a step only has to start with its reviewed argv
  (`argv[:len(expected)] == expected`).
  Red (provisioner): "tampered steps (host privilege) ran or asked".
- M13. Break: drop the `gaming-dirty` entry from the provisioner's
  `PROFILE_PLAYBOOKS`.
  Red (provisioner): "the provisioner's reviewed profiles differ from
  hyperlabctl's table".
- M14. Break: `run_step()` catches `ZeroDivisionError` instead of
  `BaseException`, so a cancelled run does not stop its playbook.
  Red (provisioner, real PTY): "the running playbook outlived SIGINT".
  The first version of the contract stayed green: the provisioner leads
  the terminal's session, so its exit hangs the terminal up and the
  recording playbook died of SIGHUP. The held playbook now ignores
  SIGHUP and records the SIGTERM it gets, with the hash file still
  present.
- M15. Break: in `resolve()`, drop the requirement that the spec is
  `vm-specs/.generated/NAME.yml`.
  Red (lifecycle): "unsafe request accepted" (a checked-in spec).
- M16. Break: the provisioner's `if rc != 0:` becomes `if False:`.
  Red (provisioner): "a failed profile pass did not stop"; red
  (integration, real bridge, runner and provisioner): "a failed
  provisioning reported success".
- M1-M16 were run again on the tree that carries the three review fixes
  below, with the same breaks (M4 and M13 on the code as it now reads)
  and the same red messages.
- M17. Break: in `run()` of `privatestack-operation.py`, the stopped
  command's wait back to `child.wait(timeout=3)` for every action.
  Red (integration, real runner and provisioner, the first profile pass
  ignoring the hangup and taking five seconds to end): "the hash file
  outlived the stopped operation"; red (lifecycle): "stop deadlines
  changed".
- M18. Break: `PROVISION_STOP_GRACE = 3`.
  Red (integration): "the hash file outlived the stopped operation"; red
  (lifecycle): "the runner may kill the provisioner before it removes the
  hash file: 3 s for 10 s".
- M19. Break: in the provisioner's signal handler (`cancel()` then,
  `Stop.handle()` now), drop the early return for a signal that is not
  the first, so every later signal raises again.
  Red (provisioner, real PTY, SIGHUP, SIGTERM and SIGINT sent while the
  cancelled playbook takes two seconds to end): "the hash file outlived
  repeated signals".
- M20. Break: in `provision_steps()`, back to plain equality, `if stored
  != project_vm_spec(root, record):`.
  Red (creation plan): "projection case boolean for integer: accepted
  what must be refused (differs from the projection)"; red (provisioner,
  real CLI): "the provisioner ran with an edited spec (float memory)".
  The contracts stop at their first red case; `vcpus true for 1` on the
  one-vCPU Machine follows in both.
- M21. Break: after the step ids are checked in `steps_for()`, take the
  profile from the plan again (`profile = plan["steps"][2]["argv"][5]`
  for a workstation).
  Red (provisioner): "tampered steps (another Template's profile) ran or
  asked".
- M22. Break: in `mapped_profile()`, drop `record.get("id") == machine`.
  Red (provisioner): "a plan with another Machine's record ran or asked".
- M1-M22 were run again on the tree that also starts each playbook
  inside `Stop.deferred()`, with the same red messages.
- M23. Break: `run_step()` back to its earlier form, `child =
  subprocess.Popen(...)` before the `try` and no deferral.
  Red (integration, the stop delivered inside `Popen()` of the first
  profile pass): "the playbook was not stopped and reaped before its hash
  file was removed", the observer showing the playbook still sleeping
  (`S`) when the file was removed and no reap of it.
- M24. Break: the provisioner's `child.kill()` after `PLAYBOOK_GRACE`
  becomes `pass`.
  Red (integration, a playbook that ignores the hangup and SIGTERM): "the
  hash file outlived the stopped operation"; the provisioner waits on the
  playbook until the runner kills it after `PROVISION_STOP_GRACE`.
- M25. Break: drop the `child.wait()` that follows `child.kill()`.
  Red (integration, the same playbook): "the playbook was not stopped and
  reaped before its hash file was removed"; the killed playbook still has
  a `/proc` entry when the file is removed.
- M26. Break: start the playbook under `held()` (the ending signals
  blocked in the kernel) instead of `Stop.deferred()`.
  Red (integration, cooperative case): "the playbook started with SIGHUP
  blocked or ignored"; the mask survives `exec`, so restoring the
  provisioner's own does not reach the playbook.
- M27. Break: `Stop.deferred()` no longer raises the signal it noted.
  Red (integration, the stop inside `Popen()`): "the hash file outlived
  the stopped operation"; the run goes on waiting on the playbook.
- M28. Break: `run_step()` cleans up without checking that a playbook was
  started (`if True:` for `if child is not None:`).
  Red (provisioner, real PTY, the first profile pass cannot be started):
  "a playbook that could not be started was not refused"; the cleanup
  fails on `None` and the run ends with a traceback instead of status 2.
- Restore: the copy goes back; the four contracts print their OK line.

### The GPU ladder state is committed without its transaction

`problems/gpu-ladder-state-write-fail-open.md`. Each break is one edit of
`roles/gpu_handoff/files/qemu`; the red check is `bats tests/hook.bats`.
The six "concurrent prepares" tests are called the races below: four on a
fresh boot, two over rung 3.

- Break: ignore the write status
  (`if ! { printf '%s\n' "${trust}" > "${temp}" || :; }; then`).
  Red: "a failed rung write refuses, keeps the old rung and leaves no
  temporary file" and "a failed first rung write records no state that
  could authorize a start" (the empty temporary file is published).
- Break: ignore the rename status (`|| :` after the `mv -f -T`).
  Red: "a failed rename refuses, keeps the old rung and leaves no
  temporary file".
- Break: ignore the `mktemp` status (`|| :` inside the substitution).
  Red: "a failed temporary file creation refuses and leaves the rung
  byte-identical" (the path check still refuses, but too late to say why).
- Break: replace the `flock -x -w` condition with `false`.
  Red: all six races; "concurrent prepares on a fresh boot: a stale clean
  commit cannot overwrite dirty" fails on `[ "$(state)" = "1" ]`, the
  stale clean commit having left rung 3. Also both "failed lock
  acquisition" tests and "an interruption while taking the lock refuses
  and records nothing".
- Break: insert `flock -u "${lock_fd}"` before the trust file is read.
  Red: all six races, again on rung 3 for the fresh-boot clean/dirty one.
- Break: insert
  `if [[ -e "${STATE_FILE}" ]]; then flock -u "${lock_fd}"; fi` there
  instead, so the lock holds only while the first rung is created.
  Red: the two races over rung 3; "a stale dev commit cannot overwrite
  dirty" fails on `[ "$(state)" = "1" ]` with rung 2, and in "dev waiting
  on a dirty commit is refused" dev is accepted. The four fresh-boot races
  stay green: they never see an existing rung.
- Break: write the rung straight to `"${STATE_FILE}"` and drop the `mv`.
  Red: twelve tests, among them the two write-failure tests (the old rung
  is truncated), the rename, interrupt and kill tests and the races.
- Break: drop `-L "${STATE_FILE}" ||` from the trust file check.
  Red: "a redirected trust file is refused and neither it nor its target
  changes".
- Break: drop `-L "${LOCK_FILE}" ||` from the first lock check.
  Red: "a redirected lock is refused and its target is not created".
- Break: drop `umask 077 &&` from the lock creation.
  Red: "the lock is created private and the published rung stays
  world-readable".
- Break: drop the `chmod 0644` (`if false; then`).
  Red: the same mode test, and "an interruption during a successful commit
  step still refuses" (its signal came from `chmod`).
- Break: disable the temporary path check (`if false && [[ ...`).
  Red: "a temporary file outside the state directory is refused and kept".
- Break: drop the first `trap 'exit 1' HUP INT TERM`, before `mkdir`.
  Red: "an interruption while taking the lock refuses and records nothing",
  on the status only: Bash still runs the EXIT trap on a fatal TERM, but
  exits 143, not 1.
- Break: drop `trap 'pending_signal=1' HUP INT TERM`.
  Red: "a signal while the temporary file is created removes it and
  refuses": the hook exits before it owns the file and leaves it behind.
- Break: drop the `trap 'exit 1' HUP INT TERM` after `owned_temp`, so the
  signal stays held for the rest of the commit.
  Red: "an interruption during a successful commit step still refuses":
  the hook publishes rung 1 and exits 0.
- Restore: `git checkout -- roles/gpu_handoff/files/qemu`.

### CI executes the local shell, palette and choices checks

`problems/ci-skipped-shell-palette-and-choices.md`.
`python tests/ci_verify_parity_contract.py` is the red check below. Run
`python tests/contract_mutations.py CiVerifyParityMutationTests` to replay the
breaks automatically on temporary copies of the two entrypoints. Each test
requires the named behavioral or structural refusal; a surviving mutation is a
failure. The baseline with every stub passing must be green, and each of the
six stubs is independently made to fail in both paths. The actual suites run
separately; successful stub runs do not certify their implementations.

The test method names below follow
`python tests/contract_mutations.py CiVerifyParityMutationTests.`; append the
method to that prefix to replay one mutation. Copy the input files before a
manual break and restore those copies afterward.

| Test method | Break in the temporary copy | Required red diagnostic |
| --- | --- | --- |
| `test_ci_shell_step_kept_only_as_its_name_and_a_comment` | Replace the shell step's run command with a comment and echo of that command; keep the display name. | `CI did not run sh tools/shell-tests/run.sh` |
| `test_ci_shell_check_behind_an_unreachable_branch` | Put the shell command inside `if false; then ...; fi`. | Same missing shell invocation |
| `test_ci_shell_check_moved_into_the_toolchain_step` | Move the shell check into the excluded installation step. | Same missing shell invocation |
| `test_ci_drops_any_palette_or_choices_command` | Remove each of the five 0g commands separately. | `CI did not run` followed by the exact removed argv |
| `test_a_required_command_may_not_run_twice` | Duplicate the palette invocation in either entrypoint. | That path `ran` the command `2 times` |
| `test_ci_palette_argument_changes` | Change `tools/palette/palette.yml` to `tools/palette/palette.yaml`. | Missing original palette argv and unexpected changed argv |
| `test_ci_surfaces_argument_changes` | Change the surfaces argument from `roles/host_desktop_sway/files/palette` to `roles/host_desktop_sway/files`. | Missing original surfaces argv and unexpected changed argv |
| `test_matching_wrong_arguments_in_both_paths_are_refused` | Change the palette argument in both entrypoints. | Missing original palette argv despite matching execution lists |
| `test_ci_palette_step_may_not_continue_on_error` | Add `continue-on-error: true` to the palette step. | Step `sets 'continue-on-error'` |
| `test_ci_shell_step_may_not_wait_for_a_manual_event` | Add `if: github.event_name == 'workflow_dispatch'` to the shell step. | Step `sets 'if'` |
| `test_ci_validation_job_may_not_be_optional` | Add `continue-on-error: true` to `validate`. | Job `sets 'continue-on-error'` |
| `test_ci_must_still_run_on_pull_requests` | Remove the pull-request trigger. | `CI must run on every push and every pull request, unfiltered` |
| `test_ci_discarded_status_hides_a_failure` | Append `|| true` to the consistency check. | `CI succeeded while` that check `failed` |
| `test_ci_discards_a_failed_child_status` | Background the shell check and discard `wait`'s result. | `CI succeeded while sh tools/shell-tests/run.sh failed` |
| `test_ci_pipe_to_tee_hides_a_failure` | Pipe the shell check to `tee` under the default shell without pipefail. | Same masked shell failure |
| `test_ci_later_success_hides_a_failure` | Use `set +e` before the palette check and append `echo done` after the last command. | `CI succeeded while` the palette check `failed` |
| `test_ci_six_checks_after_a_failing_step_are_skipped` | Move the shell and palette/choices steps back after the discovered structural contracts step. | `CI skipped` the six checks `when python 'tests/*_contract.py' failed` |
| `test_verify_discarded_status_hides_a_failure` | Replace `run python3 tools/choices/choices.py check` with an unchecked command and discarded status. | `verify.sh exited 0 while` that check `failed` |
| `test_verify_drops_the_shell_check` | Remove the local shell check. | `CI and verify.sh run different tool checks` |
| `test_verify_gains_a_check_ci_does_not_run` | Add a stubbed invocation of a nonexistent extra palette script locally. | Same divergent execution diagnostic |
| `test_ci_duplicate_yaml_key_is_refused` | Duplicate the shell step's `run` key. | `duplicate YAML key` |
| `test_ci_duplicate_step_id_is_refused` | Give the shell step the existing `structural_contracts` id. | `duplicate step id` |
| `test_redirected_entrypoints_are_refused` | Replace either entrypoint with a symlink to an identical copy. | `entrypoint must be a regular, unredirected file` |
| `test_ci_unmodelled_shell_is_refused` | Supply a YAML mapping as the shell setting. | `uses shell` with a refusal, without a traceback |

All listed breaks were observed red on temporary copies and restored green.
Before the input validation fix, duplicate keys, duplicate step ids and both
redirected files stayed green, and the malformed shell raised TypeError; the
new mutation tests exposed these gaps and now pass. The six steps first sat
after the structural contracts step: with every other stub made to fail in
turn, `ruff`, `ansible-lint`, the syntax check and the contract loop each
skipped all six, and moving the steps right after the toolchain turned that
check green. The earlier committed CI
workflow, with only its toolchain id added for the fixture, was also observed
red for all six missing invocations, then green after restoring the new steps.

### verify.sh runs the unprivileged render invariants without sudo

`python tests/verify_render_selection_contract.py` is the red check below. It
runs the shipped `verify.sh` in a temporary checkout where every tool it calls,
`sudo` included, is a recording stub, with stdin redirected and stdout either a
pipe or a terminal, since the render suite is invoked from one place for each.
Its cases are a run without any credential (passing, with a failing render
suite, with a failing `ruff`), a supplied password file (passing, failing),
passwordless sudo (passing, failing) and a supplied file that is missing or,
when not run as root, mode 0. Run
`python tests/contract_mutations.py VerifyRenderSelectionMutationTests` to
replay the breaks automatically on a temporary copy of `verify.sh`; append the
method name to that prefix to replay one. The stubs do not certify the render
suite itself: `ansible-playbook -i inventory.ini tests/render.yml` still has to
pass with credentials.

| Test method | Break in the temporary copy | Required red diagnostic |
| --- | --- | --- |
| `test_no_credentials_returns_before_the_render_suite` | Put back `fail=1` and `return` in place of the partial selection. | `partial success (pipe): render suite ran [], expected` the `--skip-tags privileged` argv |
| `test_partial_run_must_skip_only_the_privileged_tag` | Set `render_select=()` in the no-credential branch. | `partial success (pipe): render suite ran` the argv without `--skip-tags privileged` |
| `test_full_runs_may_not_skip_the_judge` | Default `render_select` to `--skip-tags privileged`, or add it to the password-file or the passwordless branch only. | `full success with a supplied file` or `passwordless full success` `render suite ran` an argv with `--skip-tags privileged` |
| `test_partial_render_failure_may_not_be_swallowed` | Call the pipe-mode render suite without `run`, or drop `fail=1` after the terminal-mode `FAIL`. | `partial render failure (pipe)` or `(terminal)`: `verdict ['VERIFICATION INCOMPLETE ...']` |
| `test_partial_success_may_not_print_all_green` | Drop `render_judge_missing` from the ALL GREEN condition. | `partial success (pipe): verdict ['ALL GREEN - ready to commit.']`, with `verify.sh exited 0, expected 1` |
| `test_failure_may_not_be_reported_as_the_missing_judge` | Test `render_judge_missing` before `fail` in the verdict. | `partial run with a lint failure (pipe): verdict ['VERIFICATION INCOMPLETE ...']` |
| `test_partial_run_must_name_the_missing_judge` | Drop the `NOT RUN` line of level 2b. | `partial success (pipe): level 2b reports the nft -c judge as not run 0 times, expected 1` |
| `test_unreadable_supplied_file_may_not_fall_back` | Test the configured file with `-r` instead of `-n`, so an unreadable one falls through. | `supplied file missing (pipe): render suite ran` the `--skip-tags privileged` argv, and `sudo ran ['sudo -n true'], expected []` |

All listed breaks were also made by hand on `verify.sh` from a saved copy:
each turned the contract red with the diagnostic above (between 4 and 20
errors), and restoring the copy turned it green. Before the change, the
contract was red only for the three no-credential cases, in both stdout modes:
the render suite was not run, the verdict was `VERIFICATION FAILED` and no
`NOT RUN` line was printed. Every full-credential case was already green.

### Roadmap hardware claims and ADR status lines name their evidence

`python tests/docs_contract.py` is the red check below. It parses every
checkbox entry of `docs/roadmap.md`, continuation lines included, and every
numbered entry of `docs/adr/README.md`. Each break was made on the real file
from a copy in a scratch directory, observed red with the message below,
then the copy was put back and the contract was green again. No broken
entry was kept. The contract proves that a claim carries a reference of the
right shape, not that the observation happened or that a receipt is enough.

| # | Break | Required red diagnostic |
| --- | --- | --- |
| D1 | Delete the `Status:` line of ADR 0018. | `0018-disposable-discards-on-stop.md has 0 Status lines, not one` |
| D2 | `srv-01` entry: `(Nitro-verified: operator-observed, unpublished)` becomes `(Nitro-verified)`; every other entry keeps its qualification. | `roadmap line N: checked hardware claim names neither an evidence: receipt nor 'operator-observed, unpublished'`, N being the `srv-01` line |
| D3 | Guest Workspace Shell entry of milestone 1: delete its continuation line `unpublished)`, so only `operator-observed,` is left. | The same message for that entry's first line: the qualification is read across the line break |
| D4 | The `evidence:` target of the `guest-arch-dev-vfio.yml` idempotence entry becomes a receipt name that does not exist. | `evidence target '...-2026-08-30.md' is not an existing file` |
| D5 | The same target becomes `../../../../../../../../etc/passwd`. | `evidence target ... escapes the repository` |
| D6 | The same target becomes `/etc/passwd`. | `evidence target '/etc/passwd' is not a relative path inside the repository` |
| D7 | The same target becomes `hyperlab-shell.md`, a guide that describes a physical acceptance. | `evidence target 'hyperlab-shell.md' is not an acceptance receipt in docs/` |
| D8 | The same target becomes `../tests/docs_contract.py`, a software contract. | The same `is not an acceptance receipt in docs/` message |
| D9 | The ADR index entry of 0017 loses its leading `proposed:`. | `ADR index entry of 0017-shell-machine-creation.md does not open with its status 'proposed'` |
| D10 | ADR 0022: `Status: proposed.` becomes `Status: decided.` | `0022-network-trust-and-gpu-policy.md: unrecognized status line 'Status: decided. ...'` |
| D11 | ADR 0017: add `Status: accepted.` below `## Context`. | `0017-shell-machine-creation.md has 2 Status lines, not one` |
| D12 | `- [x] physical Quickshell per-screen panel creation` becomes `- [X] ...`. | `roadmap line N: unknown checkbox mark [X]` |
| D13 | ADR 0018: insert a paragraph between the title and the `Status:` line. | `0018-disposable-discards-on-stop.md: the Status line is not right below the title` |

D4 to D8 break the one entry that has a receipt. That entry also says
`operator-observed, unpublished` for its later run, and it still fails: a
bad `evidence:` target is refused whatever else the entry says. Restore:
`git checkout -- docs/roadmap.md docs/adr/`.

Blank lines keep a checkbox's context for a later indented paragraph. The
paragraph regression in `tests/docs_contract.py` covers empty and space-only
blank lines, further continuation paragraphs, and boundaries formed by an
unindented paragraph, a heading or an ordinary list item. A later checked
observation keeps its own qualification; it cannot qualify the earlier one.
The regression initially failed with `unqualified second-paragraph hardware
claim was accepted`.

| # | Break | Required red diagnostic |
| --- | --- | --- |
| D14 | Move the Guest Workspace Shell entry's existing Nitro observation to a second indented paragraph, then remove only its `operator-observed, unpublished` qualification. All other observations stay qualified. | `roadmap line 181: checked hardware claim names neither an evidence: receipt nor 'operator-observed, unpublished'` |
| D15 | In `checkbox_entries`, reset the active indentation at a blank line, restoring the old paragraph boundary behavior. | `unqualified second-paragraph hardware claim was accepted` |

For D14, the existing observation with its qualification in the second
paragraph was green before removing the qualification. D14 and D15 then
turned the full documentation contract red with the diagnostics above;
restoring each file from its saved copy, checking identical bytes, and
rerunning the contract was green. Neither mutation stayed green. These
formatting checks add no observation or hardware evidence.

### Rollback keeps a replacement spec with identical bytes

`tests/c10_machine_create_plan_contract.py` runs the real staged creation
through the bridge and CLI. The `copy-spec` fault runs after the real
`os.link` publication, before the injected directory-fsync failure. It
allocates the replacement while the original still exists and records
both files independently with `lstat`, exact bytes and SHA-256. The case
requires different device/inode identities, identical bytes and digests,
removal of this creation's record under the registry lock, preservation of
the replacement's identity and original bytes, `cleanup incomplete`, no
operation launch and unchanged unrelated state. The ordinary fsync failure
still removes the record and unmodified spec; the different-bytes spec
replacement and identical-bytes record replacement cases remain covered.

Break only `_remove_staged_spec` in a disposable copy: compare the digest
component instead of the full device/inode/digest tuple. Run the contract
through its normal main entrypoint. From the repository root, these
commands copy only fixture inputs and code, back up the production file,
apply that single mutation, require the specific preservation failure,
restore from the backup and run the same entrypoint green:

```bash
HL_SPEC_TEST_ROOT=$(mktemp -d) || exit 1
python - "$HL_SPEC_TEST_ROOT/repo" "$HL_SPEC_TEST_ROOT/machine.py.intact" <<'PY' || exit 1
import os
import shutil
import subprocess
import sys
from pathlib import Path

source = Path.cwd()
fixture, backup = (Path(value).resolve() for value in sys.argv[1:])
fixture.mkdir()
for relative in ("tests", "tools", "images", "templates"):
    shutil.copytree(source / relative, fixture / relative,
                    ignore=shutil.ignore_patterns("__pycache__", ".ruff_cache"))
bridge = Path("roles/host_desktop_common/files/privatestack-machine-actions.py")
(fixture / bridge).parent.mkdir(parents=True)
shutil.copy2(source / bridge, fixture / bridge)
target = fixture / "tools/hyperlabctl/hyperlabctl/commands/machine.py"
backup.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(target, backup)
old = "if _identify(\n            path\n        ) != staged:"
new = "if _identify(\n            path\n        )[2] != staged[2]:"
intact = target.read_text()
assert intact.count(old) == 1
command = [sys.executable, "tests/c10_machine_create_plan_contract.py"]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
try:
    target.write_text(intact.replace(old, new))
    red = subprocess.run(command, cwd=fixture, env=env, text=True,
                         capture_output=True, check=False)
    print(f"Digest-only mutation exit: {red.returncode}", flush=True)
    print(red.stdout + red.stderr, flush=True)
    assert red.returncode != 0
    assert "['fsync', 'copy-spec']: the same-bytes replacement spec was removed" in red.stderr
finally:
    shutil.copy2(backup, target)
assert target.read_bytes() == (source / target.relative_to(fixture)).read_bytes()
green = subprocess.run(command, cwd=fixture, env=env, text=True,
                       capture_output=True, check=False)
print(f"Restored full identity exit: {green.returncode}", flush=True)
print(green.stdout + green.stderr, flush=True)
assert green.returncode == 0
PY
rm -r -- "$HL_SPEC_TEST_ROOT" || exit 1
```

Observed red: exit 1, after the fixture's different-inode and equal-byte
and digest assertions passed:
`AssertionError: ['fsync', 'copy-spec']: the same-bytes replacement spec was removed: refused: hyperlabctl: Machine record directory durability is uncertain`.
Restored full tuple comparison: exit 0,
`C10 Machine create-plan and intent contract: OK`.
The working production source was never changed. These are temporary
software fixtures, with no fault injection into an installed registry.

### Guest-access refusal uses the actual Ansible conditions

`python tests/guest_access_close_contract.py` evaluates the real named tasks'
`failed_when` with Ansible's `Templar.evaluate_conditional`, using independent
registered-result fixtures. Only playbook source is trusted as a template;
fixture results remain data. The twenty rows cover guest-exec (including mixed
case and disabled text only in stdout), sudo and the pinned host key. A valid
control must return the expected boolean; missing, truncated or null key data
must instead raise an explicit Ansible error. An evaluation error on a valid
control is a failure, not a refusal control passing.

That discovered contract also runs the six mutations below on temporary copies
of the actual YAML inputs. Clean controls pass before and after each break;
the temporary input is restored from its saved bytes, and the production bytes
must remain identical. `python tests/contract_mutations.py
GuestAccessConditionMutationTests` replays them individually with the same
evaluator. Append the method name below to select one test.

| Test method | Break in temporary YAML | Observed red assertion |
| --- | --- | --- |
| `test_guest_exec_or_changed_to_and` | Replace the guest-exec `or` with `and`. | `guest-exec / successful execution with disabled stderr: expected refusal, got success` and `guest-exec / unavailable agent: expected refusal, got success` |
| `test_guest_exec_constant_false` | Set the guest-exec condition to YAML `false`. | `guest-exec / successful execution: expected refusal, got success` and the unavailable-agent row |
| `test_guest_exec_omits_stderr` | Keep only the guest-exec rc comparison. | `guest-exec / unavailable agent: expected refusal, got success` |
| `test_guest_exec_constant_true` | Set the guest-exec condition to YAML `true`. | `guest-exec / disabled stderr: expected success, got refusal` (also the mixed-case row) |
| `test_sudo_comparison_reversed` | Reverse the sudo rc equality. | `sudo / passwordless success: expected refusal, got success` and `sudo / password required: expected success, got refusal` |
| `test_pinned_lookup_rc_omitted` | Remove the pinned-key lookup rc term. | `pinned key / failed lookup with matching output: expected refusal, got success` |

The or-to-and regression was first observed red against the old contract:
`AssertionError not raised`. The old substring oracle accepted that weakened
input. After replacing only the condition oracles, every listed mutation was
also made in a separate temporary checkout and checked by
`python tests/guest_access_close_contract.py`: exit 1 at the rows above, then
`Guest access close contract: OK` after restoring the saved copy. No mutation
stayed green. Both false success and false refusal are tested.

A further manual break kept only the pinned-key rc comparison. It was red
for `pinned key / mismatched key: expected refusal, got success` and for
`pinned key / missing host-key stdout: expected Ansible rejection, got False`
(also the truncated, null and malformed key-result rows). Restoring the saved
YAML made the contract green. A boolean success cannot replace rejection of
unusable key data.

The same mutation class refuses missing or duplicated named tasks, missing
guards or registers, empty or malformed guards, expression evaluation errors,
missing or unreadable input files, symlinks and duplicate YAML guard keys.
Manual breaks were also observed red for each of these kinds of input, then
restored green. The diagnostics were respectively `expected exactly one named
task, got 0` or `got 2`, `missing failed_when`, `registered result changed`,
`malformed failed_when`, `Ansible rejected a valid control`, `condition input
rejected`, `readable regular file`, `must not be redirected` and `duplicate
YAML key 'failed_when'`.

The existing policy and order checks remain. Separate temporary-copy breaks
of the password-bearing-account guard, visudo validation and become after
NOPASSWD removal were observed red at `NOPASSWD is removed even when the
account has no password`, `the password rule is not validated before NOPASSWD
goes` and `a task after the NOPASSWD removal still needs passwordless become`;
each restored control was green. Preserve literal multiline configuration
strings when serializing these manual fixtures: changing their YAML quoting
can trip an older configuration text check before the intended order check.
This condition proof does not retire other source-text checks, observe live
access or close the disposable Machine's later boots.

## Selected Machine private diagnostics

These mutations execute the real bridge/collector boundary or the real QML
pane, state and production transport handlers with inert process I/O. They
never collect host logs or contact a Machine. The script copies the target
into a disposable fixture, backs it up before breaking it, runs the named
behavioral check red, restores the copy, and runs the same check green. Run
from the repository root; Qt 6 qmlscene is required. No Git restoration is
used and production files are never mutated.
The operation fixture also carries the real runner and provisioner so its
restored run exercises the full provisioning chain.

Expected failures:

| Mutation | Predicted behavioral failure |
| --- | --- |
| `execution-recheck` | `execution recheck allowed a stale capability for external` (and changed identities) |
| `foreign-request` | `foreign diagnostics id was accepted` in the pane/state selection scenario |
| `archive-validation` | `invalid collector result succeeded` for missing, symlink and public archives |
| `partial-count` | `partial collection was hidden` and the unreachable-guest assertion |
| `duplicate-request` | `production diagnostics duplicate guard allowed another launch` |
| `timeout-settlement` | `production timeout left diagnostics permanently busy` |
| `output-redirection` | `redirected output directory reached the collector` |
| `lifecycle-subprocess` | `managed dispatch spawned a child` before any external command runs |
| `collector-reaping` | `collector timeout/interruption did not terminate and reap its process group` |
| `collector-interruption` | `collector interruption handler was not installed` |
| `collector-kill-escalation` | timeout process-group sequence lacks SIGKILL before the final communicate |
| `collector-handler-restore` | `collector did not restore the previous signal handlers` |
| `archive-replay` | `successful JSON reused an archive from before the launch` |
| `module-subprocess`, `main-subprocess`, `class-subprocess` | AST spawners include `<module>` or `launch` outside `collect_diagnostics` |
| `capability-extra-probe` | `diagnostics capability CLI probe cost changed` |
| `startup-settlement` | `failed-to-start diagnostics did not settle at the short bound` |
| `collector-scope` | CLI `guest_manifest_scope`, `guest_archive_scope`, `host_manifest_scope` and `host_archive_scope` |

Exact mutations and checks (every restored run must exit zero):

```bash
python - <<'PY'
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
bridge = Path('roles/host_desktop_common/files/privatestack-machine-actions.py')
qml = Path('roles/host_desktop_common/files/quickshell/hyperlab')
collector = Path('tools/hyperlabctl/hyperlabctl/commands/diagnostics.py')
archive_start = '    fd = os.open(expected, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)\n'
bridge_text = (root / bridge).read_text()
archive_block = bridge_text[bridge_text.index(archive_start):bridge_text.index('    return {"phase": "diagnostics"')]
cases = [
    ('execution-recheck', bridge,
     '    action_id = diagnostics_action(name, machine, spec_row)\n',
     '    action_id = "machine.diagnostics"\n', 'bridge'),
    ('foreign-request', qml / 'ShellState.qml',
     'request === null || request.id !== requestId || request.machine !== machine',
     'request === null || request.machine !== machine', 'pane'),
    ('archive-validation', bridge, archive_block, '', 'bridge'),
    ('partial-count', bridge,
     '"unavailable": len(payload["missing"])', '"unavailable": 0', 'bridge'),
    ('duplicate-request', qml / 'MachineActions.qml',
     'machineActions.diagnosticsBusy || !/^[a-z0-9]', 'false || !/^[a-z0-9]', 'transport'),
    ('timeout-settlement', qml / 'MachineActions.qml',
     '                    machineActions.finishDiagnostics(collectionRunner, -1, 1);',
     '                    return;', 'transport'),
    ('output-redirection', bridge,
     '        if not stat.S_ISDIR(info.st_mode):',
     '        if False:', 'bridge'),
    ('lifecycle-subprocess', bridge,
     '        privileged(action_id, name)\n',
     '        subprocess.Popen(argv)\n        privileged(action_id, name)\n', 'operation'),
    ('collector-reaping', bridge, '            if not completed:', '            if False:', 'bridge'),
    ('collector-interruption', bridge,
     'handlers = {sig: signal.signal(sig, interrupted)',
     'handlers = {sig: signal.getsignal(sig)', 'bridge'),
    ('collector-kill-escalation', bridge,
     'os.killpg(process.pid, signal.SIGKILL)', 'os.killpg(process.pid, signal.SIGTERM)', 'bridge'),
    ('collector-handler-restore', bridge,
     '                signal.signal(sig, handler)', '                pass', 'bridge'),
    ('archive-replay', bridge, ' or expected.name in previous', '', 'bridge'),
    # Guard module and main calls so importing a broken fixture cannot spawn.
    ('module-subprocess', bridge, 'if __name__ == "__main__":',
     'if False:\n    subprocess.Popen(["true"])\n\nif __name__ == "__main__":', 'operation'),
    ('main-subprocess', bridge, 'if __name__ == "__main__":',
     'if __name__ == "__main__":\n    subprocess.Popen(["true"])', 'operation'),
    ('class-subprocess', bridge, 'if __name__ == "__main__":',
     'class FixtureSpawn:\n    def launch(self):\n        subprocess.Popen(["true"])\n\n'
     'if __name__ == "__main__":', 'operation'),
    ('capability-extra-probe', bridge, '        payload = cli_json("machine", "inventory")',
     '        cli_json("machine", "inventory")\n        payload = cli_json("machine", "inventory")', 'bridge'),
    ('startup-settlement', qml / 'MachineActions.qml',
     'if (machineActions.diagnosticsRunner !== collectionRunner',
     'if (true || machineActions.diagnosticsRunner !== collectionRunner', 'transport'),
    ('collector-scope', collector, '"host-and-guest" if with_guest else "host-only"',
     '"host-only" if with_guest else "host-and-guest"', 'cli'),
]
with tempfile.TemporaryDirectory(prefix='hyperlab-diagnostics-mutations-') as temporary:
    fixture = Path(temporary)
    shutil.copytree(root / qml, fixture / qml)
    shutil.copytree(root / 'tools/hyperlabctl/hyperlabctl', fixture / 'tools/hyperlabctl/hyperlabctl',
                    ignore=shutil.ignore_patterns('__pycache__'))
    (fixture / bridge).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / bridge, fixture / bridge)
    for name in ('privatestack-operation.py', 'privatestack-machine-provision.py'):
        shutil.copy2(root / bridge.parent / name, fixture / bridge.parent / name)
    for name, relative, old, new, check in cases:
        target = fixture / relative
        backup = fixture / (name + '.backup')
        shutil.copy2(target, backup)
        original = target.read_text()
        assert original.count(old) == 1, (name, 'mutation anchor is not unique')
        if check == 'operation':
            code = ('import host_operation_integration_contract as t; '
                    f't.FILES = __import__("pathlib").Path({str((fixture / bridge).parent)!r}); '
                    't.main()')
        elif check == 'bridge':
            code = ('import host_machine_actions_bridge_contract as t; '
                    f't.BRIDGE = __import__("pathlib").Path({str(fixture / bridge)!r}); '
                    'raise SystemExit(t.main())')
        elif check == 'cli':
            code = 'import harness, test_diagnostics; harness.main([test_diagnostics])'
        else:
            code = ('import host_quickshell_runtime_contract as r; '
                    f'r.QML = __import__("pathlib").Path({str(fixture / qml)!r}); ')
            if check == 'transport':
                code += 'import host_operation_qml_contract as t; t.main()'
            else:
                code += ('p = r.stage(); '
                         's, m = r.scenario_source(1920, 1080, r.machines(6), r.MACHINE_DIAGNOSTICS); '
                         'r.run("/usr/lib/qt6/bin/qmlscene", p, "machine-diagnostics", s, m); '
                         '__import__("shutil").rmtree(p)')
        env = {**os.environ, 'PYTHONPATH': str(root / 'tests'), 'HYPERLAB_REQUIRE_QML_RUNTIME': '1'}
        if check == 'cli':
            env['PYTHONPATH'] = os.pathsep.join((str(fixture / 'tools/hyperlabctl'),
                                               str(root / 'tools/hyperlabctl/tests')))
        try:
            target.write_text(original.replace(old, new))
            red = subprocess.run([sys.executable, '-c', code], env=env, check=False)
            print(name, 'mutated exit', red.returncode, flush=True)
            assert red.returncode != 0, (name, 'mutation stayed green')
        finally:
            shutil.copy2(backup, target)
        green = subprocess.run([sys.executable, '-c', code], env=env, check=False)
        print(name, 'restored exit', green.returncode, flush=True)
        assert green.returncode == 0, (name, 'restoration failed')
PY
```

The malformed/foreign JSON, zero-exit-without-result and interruption cases
are also executed by the normally discovered bridge and production transport
contracts. The archive-validation mutation specifically proves that exit
zero and a plausible manifest cannot substitute for a real private archive.
The replay case returns the same zero-exit JSON and leaves the older archive
untouched. Cleanup cases invoke installed signal handlers without delivering
real signals and assert TERM, bounded communicate, KILL escalation and final
reaping, as well as restoration of previous handlers. Spawn mutations are
inert when imported; the AST scans the entire module and attributes every
call to its innermost enclosing function, including class methods. The CLI
scope case imports a disposable copy of the collector and checks returned
and archived manifests without relying on bridge coverage.
Fixtures prove no installed-shell or Nitro/Predator observation.

## Host emergency key remains unbound

`tests/host_key_sheet_contract.py` renders the production Lua with independent
fixture inputs and executes it with real Lua and inert recording dispatchers.
It rejects panic engagement on every chord before checking sheet parity.
Every bound command is split into simple commands, shell payloads are split
again, and the words after `hyperlabctl` are read by the real hyperlabctl
parser, so global options and shell quoting cannot hide `panic engage`. The
contract first checks that matcher on fixed spellings it must and must not
flag.
Ordinary lock, key sheet and clipboard bindings are positive controls. The
real offscreen launcher must retain those rows, offer no emergency row and
run nothing when a key row is activated.

Run the following from the repository root. All mutations happen in temporary
copies; each original is copied before breaking it and restored from that copy.
Every red run must exit nonzero with the named reason, and every restored run
must pass, including the real QML runtime. No registered command runs.

```bash
python - <<'PY'
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

root = Path.cwd()
template = Path('roles/host_desktop_hyprland/templates/hyprland.lua.j2')
sheet = Path('roles/host_desktop_common/files/quickshell/hyperlab/HostKeys.qml')
contract = Path('tests/host_key_sheet_contract.py')
old_bind = '''hl.bind(
    main_mod .. " + SHIFT + Escape",
    hl.dsp.exec_cmd(
        "/usr/local/bin/hyperlabctl panic engage"
    )
)
'''
old_row = ('            { "keys": "SUPER+SHIFT+Escape", "does": "Emergency stop: '
           'cut every running Machine\'s network, then pause it; Restore is in the shell" },\n')
lock_bind = '''hl.bind(
    main_mod .. " + Escape",
    hl.dsp.exec_cmd(
        "/usr/local/bin/privatestack-lock"
    )
)
'''
keys_bind = '''hl.bind(
    main_mod .. " + F1",
    hl.dsp.exec_cmd(
        "/usr/bin/qs -c hyperlab ipc call launcher keys"
    )
)
'''
mutations = [
    ('old emergency bind', template, lambda s: s + '\n' + old_bind,
     'production Lua binds panic engage in global: SUPER + SHIFT + Escape'),
    ('different chord', template,
     lambda s: s + '\n' + old_bind.replace('SHIFT + Escape', 'SHIFT + F12'),
     'production Lua binds panic engage in global: SUPER + SHIFT + F12'),
    *[(name, template,
       lambda s, command=command: s + '\n' + old_bind.replace(
           'SHIFT + Escape', 'SHIFT + F12').replace(
               '"/usr/local/bin/hyperlabctl panic engage"', json.dumps(command)),
       'production Lua binds panic engage in global: SUPER + SHIFT + F12')
      for name, command in (
          ('JSON global option', '/usr/local/bin/hyperlabctl --json panic engage'),
          ('no-color global option', '/usr/local/bin/hyperlabctl --no-color panic engage'),
          ('repo global operand', '/usr/local/bin/hyperlabctl --repo fixture panic engage'),
          ('repo global assignment', '/usr/local/bin/hyperlabctl --repo=fixture panic engage'),
          ('interleaved globals',
           '/usr/local/bin/hyperlabctl panic --json --repo fixture engage --no-color'),
          ('sh payload', "sh -c '/usr/local/bin/hyperlabctl panic engage'"),
          ('bash payload', "/usr/bin/bash -c '/usr/local/bin/hyperlabctl --json panic engage'"),
          ('dash payload', "dash -c '/usr/local/bin/hyperlabctl --repo=fixture panic engage'"),
          ('nested shell payload',
           '''sh -c "bash -c '/usr/local/bin/hyperlabctl --no-color panic engage'"'''),
          ('shell command sequence', "sh -c '/usr/local/bin/hyperlabctl --json panic engage; :'"),
      )],
    ('matcher ignores shell payloads', contract,
     lambda s: s.replace('nested.extend(simple_commands(payload, depth + 1))', 'pass'),
     "the panic matcher missed \"sh -c 'true && hyperlabctl --json panic engage; :'\""),
    ('matcher skips global normalization', contract,
     lambda s: s.replace('parse_args(cli._normalize_global_options(list(arguments)))',
                         'parse_args(list(arguments))'),
     "the panic matcher missed 'hyperlabctl panic --no-color engage --repo=/srv/lab'"),
    ('matcher ignores shell operators', contract,
     lambda s: s.replace('if token and set(token) <= OPERATORS:', 'if False:'),
     "the panic matcher missed \"sh -c 'true && hyperlabctl --json panic engage; :'\""),
    ('orphan sheet row', sheet,
     lambda s: s.replace('        { "title": "Session and appearance", "keys": [\n',
                         '        { "title": "Session and appearance", "keys": [\n' + old_row),
     'the sheet promises SUPER+SHIFT+Escape, which is not bound'),
    ('missing lock', template, lambda s: s.replace(lock_bind, ''),
     'production Lua lost SUPER + Escape -> /usr/local/bin/privatestack-lock'),
    ('retargeted lock', template,
     lambda s: s.replace('"/usr/local/bin/privatestack-lock"', '"foot"'),
     'production Lua lost SUPER + Escape -> /usr/local/bin/privatestack-lock'),
    ('missing key sheet', template, lambda s: s.replace(keys_bind, ''),
     'production Lua lost SUPER + F1 -> /usr/bin/qs -c hyperlab ipc call launcher keys'),
    ('Lua syntax error', template, lambda s: s + '\nthis is invalid Lua !\n',
     'production Lua did not execute'),
]
with tempfile.TemporaryDirectory(prefix='hyperlab-key-mutations-') as directory:
    tree = Path(directory)
    for path in (template, Path('tests/host_key_sheet_contract.py'),
                 Path('tests/host_quickshell_runtime_contract.py'),
                 Path('themes/trust-model/rendered/hyperlab-palette-quickshell.json')):
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, tree / path)
    shutil.copytree(root / sheet.parent, tree / sheet.parent)
    shutil.copytree(root / 'tools/hyperlabctl/hyperlabctl', tree / 'tools/hyperlabctl/hyperlabctl',
                    ignore=shutil.ignore_patterns('__pycache__'))
    backups = tree / 'backups'
    backups.mkdir()
    for path in (template, sheet, contract):
        shutil.copy2(tree / path, backups / path.name)
    for name, path, mutate, expected in mutations:
        target = tree / path
        backup = backups / path.name
        original = backup.read_bytes()
        try:
            broken = mutate(original.decode())
            assert broken.encode() != original, name
            target.write_text(broken)
            red = subprocess.run(
                [sys.executable, str(tree / 'tests/host_key_sheet_contract.py')],
                capture_output=True, text=True, check=False,
                env={**os.environ, 'HYPERLAB_REQUIRE_QML_RUNTIME': '1'},
            )
            assert red.returncode != 0 and expected in red.stdout + red.stderr, (name, red)
        finally:
            shutil.copy2(backup, target)
        green = subprocess.run(
            [sys.executable, str(tree / 'tests/host_key_sheet_contract.py')],
            capture_output=True, text=True, check=False,
            env={**os.environ, 'HYPERLAB_REQUIRE_QML_RUNTIME': '1'},
        )
        assert green.returncode == 0, (name, green)
        print(name + ': red observed; restored green')
PY
```

Observed: all twenty mutations fail with their named reason and return
green following restoration. Before the matcher read the real parser, the
`JSON global option` and `sh payload` mutations failed only on sheet parity,
without the panic diagnostic: the binding itself went unnoticed. With only the old row restored, the real offscreen
scenario also fails with `the real key sheet offered an emergency shortcut`
when run independently of the earlier parity check; the original row was
present for this test before removal. The complete host-key contract then
passes with `HYPERLAB_REQUIRE_QML_RUNTIME=1`.

To exercise the real QML rejection independently of the earlier parity check,
restore the old row only in the staged component, then copy it back and rerun.
Both runs load the same staged path, and copying the original back also
restores its timestamp, so Qt's QML disk cache can serve the broken
component's compiled form to the restored run. That run then fails with the
same emergency-row error although the file is correct. The disk cache stays
off for this snippet:

```bash
QML_DISABLE_DISK_CACHE=1 PYTHONPATH=tests HYPERLAB_REQUIRE_QML_RUNTIME=1 python - <<'PY'
import shutil

import host_key_sheet_contract as keys

runner = shutil.which('qmlscene', path='/usr/lib/qt6/bin') or shutil.which('qmlscene6')
assert runner, 'Qt 6 qmlscene is required'
directory = keys.runtime.stage()
try:
    target = directory / 'HostKeys.qml'
    backup = directory / 'HostKeys.original'
    shutil.copy2(target, backup)
    row = ('            { "keys": "SUPER+SHIFT+Escape", "does": "Emergency stop: '
           'cut every running Machine\'s network, then pause it; Restore is in the shell" },\n')
    original = target.read_text()
    broken = original.replace('        { "title": "Session and appearance", "keys": [\n',
                              '        { "title": "Session and appearance", "keys": [\n' + row)
    assert broken != original
    source, messages = keys.runtime.scenario_source(
        1920, 1080, keys.runtime.machines(4), keys.SCENARIO,
    )
    try:
        target.write_text(broken)
        try:
            keys.runtime.run(runner, directory, 'host-keys-old-row', source, messages)
        except SystemExit as error:
            assert 'the real key sheet offered an emergency shortcut' in str(error), error
            print(str(error))
        else:
            raise AssertionError('the real QML accepted the emergency row')
    finally:
        shutil.copy2(backup, target)
    keys.runtime.run(runner, directory, 'host-keys-restored', source, messages)
finally:
    shutil.rmtree(directory)
PY
```

Observed: the old row fails with the named QML error; the restored component
passes (`runtime scenario OK: host-keys-restored`).


## Guest fullscreen behavioral consolidation

`python tools/hyperlabctl/tests/run.py` discovers the single behavioral module
`tools/hyperlabctl/tests/test_vm_guest_fullscreen.py`. The repository contract
`python tests/hyperlabctl_contract.py` still runs that component suite and
propagates its failures. An injected failing fullscreen assertion was observed
to make the repository contract exit 1; restoring the test returned exit 0.

The shared fixture runs the actual embedded transaction in subprocesses with
real temporary receipts, journals and locks. Its compositor interprets the
actual dispatch selector/action, including an address selector for the identity
mutation. It does not implement transaction success or recovery. Delayed
application workers belong to the parent fixture. Context managers restore
patches, reap children and remove files even after an assertion raises.

Slow-start cases retain the 0.6 s and 1.2 s startup delays. The accumulated-stage
case advances a controlled clock; the held-lock case advances the same clock
on each poll and observes refusal within the 0.2 s budget plus one 0.05 s poll,
while its real holder remains alive until explicit release. The query-timeout
case observes the actual instances, active-window and clients subprocess
timeouts and requires at most 2.0 s for each. Both concurrent cases also delay
the second interpreter by 2.5 s; larger
fixture caps on the first transaction let the handshake decide ordering.
The 10 s subprocess watchdog bounds cleanup, not acceptable startup speed.
All source fault injection uses one helper that compiles the result and refuses
missing or ambiguous targets.

The following independent mutations run the complete fullscreen module through
the ordinary harness. Each must exit 1 with its intended assertion below, then
exit 0 after restoring the saved bytes. Nominal on/off/toggle, maximized modes
and no-dispatch controls run alongside the refusal cases.

| Mutation | Break in disposable copy | Expected red assertion |
| --- | --- | --- |
| `receipt_identity` | Accept another operation id in a terminal receipt. | `terminal_receipt_wrong_operation` |
| `terminal_redispatch` | Ignore the terminal receipt and execute the recorded id again. | `sequential_dispatches` |
| `address_only` | Select the reused address instead of the stable window id. | `address_reuse_before_dispatch_state` |
| `ack_as_completion` | Finalize success before obtaining post-dispatch proof. | `ack_without_proof_status` |
| `stale_launch_budget` | Reuse the timeout from before persisting dispatching. | `persistence_launch_budget_reduced` |
| `lost_rollback_journal` | Remove the journal when the rollback write raises. | `rollback_write_failure_barrier` |
| `injection_uniqueness` | Disable the source-anchor cardinality guard. | `fault_target_missing` (also `fault_target_ambiguous`) |
| `fixture_file_cleanup` | Stop closing the fixture cleanup stack. | `cleanup_files_removed` |
| `stale_version_import` | Add a guarded import from a removed version. | `fullscreen_no_version_import` |
| `cleanup_reaping` | Stop reaping the fixture's child processes. | `cleanup_child_reaped` |
| `patch_restoration` | Detach the patch cleanup stack before yielding. | `patch_restored__run_fullscreen_remote` |
| `duplicate_definition` | Append a second definition of an existing test. | `fullscreen_no_shadowed_tests` |
| `duplicate_family` | Add another discoverable fullscreen module. | `fullscreen_single_discovery_owner` |
| `shared_lock_deadline` | Use only the 3 s lock cap, ignoring the shared transaction deadline. | `normal_start_lock_shared_deadline` (also `slow_start_lock_shared_deadline`) |
| `default_query_cap` | Raise the per-command default cap from 2 s to 7 s. | `instances_query_timeout_cap` (also `activewindow_query_timeout_cap`) |
| `client_query_cap` | Raise the explicit clients-query cap from 0.5 s to 7 s. | `clients_query_timeout_cap` |
| `concurrent_startup_margin` | Restore the first fixture dispatch's 2 s cap while the second interpreter starts slowly. | `test_concurrent_replay_dispatches_once` and `test_synchronous_completion_orders_opposite_request`, both missing the lock-wait handshake |

From the repository root, run this command; it changes only disposable copies,
backs up each target before injection, and restores it before the green run:

```bash
python - <<'PY'
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path.cwd()
VM = Path('hyperlabctl/commands/vm.py')
TEST = Path('tests/test_vm_guest_fullscreen.py')
MUTATIONS = [
    ('receipt_identity', VM, [
        ('    if operation_id != expected_operation_id:\n', '    if False:\n'),
    ], 'terminal_receipt_wrong_operation'),
    ('terminal_redispatch', VM, [
        ('    terminal = load_receipt(operation_id, requested)\n', '    terminal = None\n'),
    ], 'sequential_dispatches'),
    ('address_only', VM, [
        ('f\'window = "stableid:{record["stable_id"]}" }})\'', 'f\'window = "address:{record["address"]}" }})\''),
    ], 'address_reuse_before_dispatch_state'),
    ('ack_as_completion', VM, [
        ('def settle_dispatched(record, *, emit_terminal):\n',
         'def settle_dispatched(record, *, emit_terminal):\n    finalize_success(record, 2 if record["desired"] else 0)\n'),
    ], 'ack_without_proof_status'),
    ('stale_launch_budget', VM, [
        ('    record = dict(record)\n    record["phase"] = "dispatching"\n',
         '    previous_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n    record = dict(record)\n    record["phase"] = "dispatching"\n'),
        ('            timeout=dispatch_timeout,\n', '            timeout=previous_timeout,\n'),
    ], 'persistence_launch_budget_reduced'),
    ('lost_rollback_journal', VM, [
        ('except Exception:\n    if current_phase in ("dispatching", "dispatched"):\n        raise SystemExit(75) from None\n',
         'except Exception:\n    if current_phase in ("dispatching", "dispatched"):\n        remove_state(operation_path)\n        raise SystemExit(75) from None\n'),
    ], 'rollback_write_failure_barrier'),
    ('injection_uniqueness', TEST, [
        ('    if count != 1:\n', '    if False:\n'),
    ], 'fault_target_missing'),
    ('cleanup_reaping', TEST, [
        ('            for child in reversed(self.children):\n                _reap(child)\n',
         '            for child in reversed([]):\n                _reap(child)\n'),
    ], 'cleanup_child_reaped'),
    ('patch_restoration', TEST, [
        ('        yield\n\n\ndef _invoke', '        stack.pop_all()\n        yield\n\n\ndef _invoke'),
    ], 'patch_restored__run_fullscreen_remote'),
    ('duplicate_definition', TEST, [], 'fullscreen_no_shadowed_tests'),
    ('duplicate_family', TEST, [], 'fullscreen_single_discovery_owner'),
    ('fixture_file_cleanup', TEST, [
        ('        finally:\n            self.stack.close()\n',
         '        finally:\n            pass\n'),
    ], 'cleanup_files_removed'),
    ('stale_version_import', TEST, [], 'fullscreen_no_version_import'),
    ('shared_lock_deadline', VM, [
        ('lock_deadline = min(\n    transaction_deadline,\n    time.monotonic() + 3.0,\n)\n',
         'lock_deadline = time.monotonic() + 3.0\n'),
    ], 'normal_start_lock_shared_deadline'),
    ('default_query_cap', VM, [
        ('def command(argv, failure_code, timeout=2.0):\n',
         'def command(argv, failure_code, timeout=7.0):\n'),
    ], 'instances_query_timeout_cap'),
    ('client_query_cap', VM, [
        ('def mode_for_target(stable_id, timeout=0.5):\n',
         'def mode_for_target(stable_id, timeout=7.0):\n'),
    ], 'clients_query_timeout_cap'),
    ('concurrent_startup_margin', TEST, [
        ('DISPATCH_TIMEOUT_SECONDS = 60.0', 'DISPATCH_TIMEOUT_SECONDS = 2.0'),
    ], 'test_concurrent_replay_dispatches_once'),
]
RUN = 'import harness, test_vm_guest_fullscreen as tests; harness.main([tests])'

def run(directory):
    result = subprocess.run([sys.executable, '-c', RUN], cwd=directory, text=True, capture_output=True,
                            env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
                                 'PYTHONPATH': str(directory / 'tests') + ':' + str(directory)}, check=False)
    log = result.stdout + result.stderr
    return result.returncode, log

results = []
for name, relative, changes, expected in MUTATIONS:
    with tempfile.TemporaryDirectory(prefix='fullscreen-mutation-') as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / 'tools/hyperlabctl/hyperlabctl', directory / 'hyperlabctl',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (directory / 'tests').mkdir()
        for filename in ('harness.py', 'test_vm_guest_fullscreen.py'):
            shutil.copy2(ROOT / 'tools/hyperlabctl/tests' / filename, directory / 'tests' / filename)
        target = directory / relative
        backup = directory / 'intact.py'
        shutil.copy2(target, backup)
        source = target.read_text()
        for old, new in changes:
            if source.count(old) != 1:
                raise AssertionError((name, 'mutation target not unique', source.count(old), old))
            source = source.replace(old, new, 1)
        extra = None
        if name == 'duplicate_definition':
            source += '\n\ndef test_dispatch_counter_counts_independent_calls() -> None:\n    equals("duplicate_control", 2, 2)\n'
        elif name == 'stale_version_import':
            source += '\nif False:\n    from test_vm_guest_fullscreen_v42 import Guest\n'
        elif name == 'duplicate_family':
            extra = directory / 'tests/test_vm_guest_fullscreen_extra.py'
            extra.write_text('"""Duplicate discovery control."""\n')
        compile(source, str(target), 'exec')
        target.write_text(source)
        red_rc, red_log = run(directory)
        if red_rc != 1 or 'FAIL ' + expected not in red_log:
            raise AssertionError((name, 'intended behavior not detected; see red log', red_rc))
        if name == 'concurrent_startup_margin':
            if ('FAIL test_synchronous_completion_orders_opposite_request' not in red_log
                    or red_log.count('AssertionError: fixture handshake not reached: lock-waiting') != 2):
                raise AssertionError((name, 'both slow-start ordering cases must fail at the handshake', red_log))
        print(name + ': RED ' + expected, flush=True)
        shutil.copy2(backup, target)
        if extra is not None:
            extra.unlink()
        green_rc, green_log = run(directory)
        if green_rc != 0:
            raise AssertionError((name, 'restore failed', green_rc, green_log))
        print(name + ': RESTORED ' + green_log.strip(), flush=True)
        results.append({'mutation': name, 'expected': expected, 'red_rc': red_rc,
                        'green_rc': green_rc, 'green': green_log.strip()})
print(json.dumps(results, indent=2))
PY
```

All seventeen mutations above were observed red at the named assertions. Each
restored module reported `passed 694, failed 0`. Both missing and ambiguous
injection targets were detected; the guarded stale import was refused by the
AST check without executing a missing module. The original 59 test functions
map to behavioral functions and named cases, with successful and no-dispatch
controls retained alongside all distinct refusal and recovery observations.
Before increasing the first transaction's fixture caps, both new 2.5 s
slow-start cases also failed at the missing lock-wait handshake. The lock-cap
mutation recorded about 3 s on the controlled clock; the query-cap mutations
passed 7.0 s to the actual subprocesses. Neither was caught by startup timing
or a cleanup watchdog. An initial command-default mutation stayed green with
a clients-only probe: the clients query passes an explicit 0.5 s cap and does
not use that default. Extending the probe to instances and active-window
queries caught the default mutation; independently changing the explicit
clients cap caught that separate path.


### Palette execution preserves JSON arguments and keeps displayed commands inert

`python tests/hyperlabctl_contract.py` executes the complete current Bash
palette in temporary subprocess fixtures. Only the fixed CLI and Python
assignments are adapted, each exactly once. Rofi and Foot are recording
stand-ins in a private PATH; Foot executes the palette's embedded Python
and prepared-command Bash payloads. The textual resolver points at a
different inert child from the JSON resolver. The expected child arguments
are chosen directly, including an empty argument, spaces, both quote
characters, semicolon, pipe, wildcard and literal substitution/backtick
text. Canaries can appear only under the temporary fixture directory.

The 14 controls cover ordinary success, an ordinary child returning 23,
the background panel, privileged display, cancellation and empty selection
at the action menu and all three target menus, and both resolver refusals.
Each checks the complete CLI/menu/terminal/child trace. Terminal completion
is a recorded handshake after executing and waiting for the payload. A
bounded pipe wait, a dedicated process group and temporary Linux child
subreaper adoption permit killing and reaping descendants on success,
assertion failure and timeout. These are software fixtures, not observations
of an installed desktop or confinement of a trusted session. The separate
Ansible-condition case is outside these fixtures; the wider textual-contract
debt remains open.

Observed with the command below (all old searched-for fragments remain,
including inert comments where the executing line changes):

| Temporary break | Behavioral assertion observed red |
|---|---|
| Ordinary `eval "$command"` instead of `run_argv` | `ordinary: textual destination executed` |
| `subprocess.call(" ".join(argv), shell=True)` | `ordinary: shell evaluation created a canary` |
| Panel `execvp` of Bash with a joined command | `panel: shell evaluation created a canary`, after terminal completion |
| Ordinary `subprocess.call(argv[:-1])` | `ordinary: exact JSON child receipt differs` (no canary needed) |
| Privileged branch falls through to JSON | `privileged display: privileged display executed the JSON destination` |
| Prepared display payload evaluates its positional command | `privileged display: textual destination executed` |
| Ordinary launch replaced with `:` | `ordinary: exact JSON child receipt differs` |
| Panel launch replaced with `:` | `panel: exact JSON child receipt differs` |

Every break was red for the stated assertion; restoring the temporary copy
passed all 14 cases after each break. The normal contract then printed
`palette argv behavior: OK`, `component suite: passed 1701, failed 0` and
`contract: passed 53, failed 0`, exit 0. Source assertions are secondary:
the command below invokes the same behavioral entrypoint directly, without
using their presence or absence as the failure oracle. No production bytes
are changed by the command. A surviving mutation raises an error.

```bash
python - <<'PY'
import importlib.util
from pathlib import Path
import shutil
import tempfile

spec = importlib.util.spec_from_file_location('palette_contract', 'tests/hyperlabctl_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = Path('roles/host_desktop_sway/files/privatestack-hyperlab-palette.sh').read_text()
run = '    run_argv "hyperlab: ${id}" "${argv_json}"'
panel = '        open_panel "${argv_json}"'
privileged = '    if [[ ${privileged} == yes ]]; then'
display = next(line for line in original.splitlines() if 'privileged - review' in line)
mutations = {
    'ordinary textual eval': (run, '    eval "$command"\n    # ' + run.strip(),
                              'ordinary: textual destination executed'),
    'ordinary joined shell': ('rc = subprocess.call(argv)',
                              'rc = subprocess.call(" ".join(argv), shell=True)\n# subprocess.call(argv)',
                              'ordinary: shell evaluation created a canary'),
    'panel joined shell': ('os.execvp(argv[0], argv)',
                           'os.execvp("/bin/bash", ["bash", "-c", " ".join(argv)])\n# os.execvp(argv[0], argv)',
                           'panel: shell evaluation created a canary'),
    'ordinary dropped argument': ('rc = subprocess.call(argv)',
                                  'rc = subprocess.call(argv[:-1])\n# subprocess.call(argv)',
                                  'ordinary: exact JSON child receipt differs'),
    'privileged JSON fallthrough': (privileged, '    if [[ no == yes ]]; then',
                                    'privileged display: privileged display executed the JSON destination'),
    'evaluated prepared display': (display,
                                   display.replace('bash -lc "', 'bash -lc "eval \\"\\$1\\"; ', 1),
                                   'privileged display: textual destination executed'),
    'ordinary execution bypass': (run, '    : # ' + run.strip(),
                                   'ordinary: exact JSON child receipt differs'),
    'panel execution bypass': (panel, '        : # ' + panel.strip(),
                                'panel: exact JSON child receipt differs'),
}
with tempfile.TemporaryDirectory(prefix='hyperlab-palette-mutations-') as directory:
    root = Path(directory)
    backup = root / 'palette.clean'
    backup.write_text(original)
    script = root / 'palette.sh'
    for name, (old, new, expected) in mutations.items():
        assert original.count(old) == 1, (name, original.count(old))
        shutil.copyfile(backup, script)
        script.write_text(script.read_text().replace(old, new, 1))
        assert 'subprocess.call(argv)' in script.read_text()
        assert '--json "${resolve_args[@]}"' in script.read_text()
        assert 'eval "$1"' not in script.read_text()
        try:
            module.palette_argv_behavior(script.read_text())
        except AssertionError as exc:
            message = str(exc)
            assert message.startswith(expected), (name, message)
            print('%s: RED: %s' % (name, message.split(': [')[0]), flush=True)
        else:
            raise AssertionError('%s stayed GREEN' % name)
        finally:
            shutil.copyfile(backup, script)
        module.palette_argv_behavior(script.read_text())
        print('%s: restored GREEN (14 cases)' % name, flush=True)
PY
```

### ESP semantic refusals use the deliberate error protocol

`python tests/vfio_boot_esp_mode_contract.py` now requires each existing
semantic refusal to return exactly 2, write exactly empty stdout, and start
stderr with `esp_file_mode: ` followed by a nonblank explanation. A Python
traceback also fails, even after a valid prefix. Each failure identifies the
input case and includes the actual return code, stdout and stderr from the
CLI subprocess. Positive mode cases and structural role checks are retained.
The earlier ESP entries above preserve their historical diagnostic wording;
the messages below describe the strengthened assertions.

Observed with disposable source copies containing the real tool, unchanged
contract entrypoint and role task/default files. Each tool file was backed
up before mutation, restored from that copy after the red run, then checked
again. Every red below is contract exit 1 at `refused()`, and every restoration
is exit 0 with `vfio_boot ESP mode contract: OK` and empty stderr. Production
tool and role files are unchanged. These synthetic CLI runs do not execute
the Ansible tasks or prove convergence of installed boot files.

- Break: remove `require(value is not None, ...)` from `mask()`.
  Before strengthening the helper, this mutation was green: the traceback
  satisfied its loose nonzero-status check. With the new helper, red:
  `the tool did not refuse a vfat mount without fmask: rc=1 stdout=''`,
  ending in `with exit 2`, with actual stderr containing
  `Traceback (most recent call last):` and
  `TypeError: expected string or bytes-like object, got 'NoneType'`.
  This is the first missing-mask case reached; execution stops before the
  missing-dmask case. Restored: green.
- Break: change the `ModeError` handler's return from 2 to 1, preserving
  its diagnostic. Red: `the tool did not refuse fmask=0000, which lets
  everyone write a boot entry: rc=1 stdout=''`, ending in `with exit 2`.
  Actual stderr is `esp_file_mode: files there would read 0777: a user
  other than root could write them` followed by a newline. Restored: green.
- Break: remove `esp_file_mode: ` from the `ModeError` diagnostic,
  preserving exit 2. Red: `the tool broke the refusal diagnostic protocol
  for fmask=0000, which lets everyone write a boot entry: rc=2 stdout=''`.
  Actual stderr is `files there would read 0777: a user other than root
  could write them` followed by a newline. Restored: green.
- Break: print `unexpected output` to stdout in the `ModeError` path,
  preserving exit 2 and the original diagnostic. Red: `the tool wrote to
  stdout while refusing fmask=0000, which lets everyone write a boot
  entry: rc=2 stdout='unexpected output\n'`, with the prefixed diagnostic
  still present in actual stderr. Restored: green.
- Break: replace the `ModeError` explanation with whitespace, preserving
  the prefix and exit 2. Red: `the tool broke the refusal diagnostic
  protocol for fmask=0000, which lets everyone write a boot entry: rc=2
  stdout='' stderr='esp_file_mode:   \n'`. Restored: green.
- Break: append `Traceback (most recent call last):` and a newline to the
  `ModeError` stderr, preserving exit 2, empty stdout and the original
  prefixed explanation. Red: `the tool emitted a traceback while refusing
  fmask=0000, which lets everyone write a boot entry: rc=2 stdout=''`, with
  both the diagnostic and traceback header in actual stderr. Restored: green.

### Native Networks stays gated, read-only and observational

The deployment contract executes the role's actual boolean assertion and copy
content against a disposable destination, parsing the generated JSON. The
read-only runtime contract executes the real bridge in a disposable copy with
an inert tracing CLI. The offscreen runtime contract instantiates the real
state, coordinator, Control Center and shared frame; its Networks scenarios
keep production completion and feature-file handlers with inert transport.
The real deadline Timer remains instantiated; timeout scenarios emit its
triggered signal without waiting for the interval.
Each source was copied before breaking it, restored from that copy and the
same predicted check rerun. All reds below were behavioral or deployment
assertions, with no syntax error or missing tool.

| Mutation | Check | Observed red assertion |
| --- | --- | --- |
| M1: Default on | `host_desktop_common_contract.py` | Networks feature must default to boolean false |
| M2: Accept string false as enabled | QML Networks disabled-page | invalid feature document enabled Networks |
| M3: Remove navigation gate | QML Networks disabled-page | disabled direct Networks navigation succeeded |
| M4: Normalize inactive to active | QML Networks rows/small viewport | inactive network normalized to active |
| M5: Normalize missing to active | QML Networks rows/small viewport | missing network normalized to active |
| M6: Treat error object as empty | QML Networks failures/freshness | malformed Networks inventory accepted |
| M7: Publish valid prefix of duplicate or bad row | QML Networks failures/freshness | malformed Networks inventory accepted |
| M8: Remove freshness guard | QML Networks failures/freshness | stale Networks observation appears current |
| M9b: Remove flight-generation admission guard | QML Networks late-answer | old Networks answer consumed the new request |
| M10: Start network instead of listing | `host_quickshell_readonly_runtime_contract.py` | network inventory exact read-only argv changed: [['net', 'start', 'lab']] |
| M11: Remove single flight admission guard | QML Networks rows/small viewport | overlapping Networks read accepted |
| M12: Leave timed-out request current | QML Networks failures/freshness | late answer after Networks timeout was published |
| M13: Remove array bound | QML Networks failures/freshness | malformed Networks inventory accepted |
| M14: Remove typed subnet check | QML Networks failures/freshness | malformed Networks inventory accepted |
| M15: Remove typed forwarding check | QML Networks failures/freshness | malformed Networks inventory accepted |
| M16: Make read-only cards unreachable with Tab | QML Networks rows/small viewport | Network rows cannot be reached with Tab |
| M17: Serialize a string instead of a boolean | `host_desktop_common_contract.py` | Networks generated document differs: {'networks_view_enabled': 'False'} |
| M18: Change installed feature mode | `host_desktop_common_contract.py` | Networks feature document deployment changed |
| M19: Accept duplicate or extra feature keys | QML Networks disabled-page | invalid feature document enabled Networks |
| M20: Remove subnet length bound | QML Networks failures/freshness | malformed Networks inventory accepted |
| M21: Remove forwarding length bound | QML Networks failures/freshness | malformed Networks inventory accepted |
| M22: Ignore a successful unchanged feature reload | QML Networks disabled-page | successful unchanged feature reload did not restore enablement |
| M23: Remove the keyboard session watcher | `host_quickshell_workspace_theme_contract.py` | session FileView watcher policy changed |
| M24: Remove the feature document watcher | `host_quickshell_workspace_theme_contract.py` | session FileView watcher policy changed |
| M25: Add an appearance theme watcher | `host_quickshell_workspace_theme_contract.py` | session FileView watcher policy changed |
| M26: Remove the feature document path | QML Networks disabled-page | Networks feature file path differs from deployment |
| M27: Disconnect the request completion deadline | QML Networks failures/deadline | Networks timeout did not become unavailable |
| M28: Extend the documented completion deadline | QML Networks disabled-page | Networks completion deadline differs from its documented bound |
| M29: Apply the shared startup-relative loading rule to Networks | QML Networks loading after shell uptime | Networks first read after shell uptime became unavailable |
| M30: Remove bridge cancellation on hide | QML Networks late-answer | Networks hide did not stop its bridge process |
| M31: Cancel on hide but omit cancellation on disable | QML Networks late-answer | Networks disable did not stop its bridge process |
| M32: Add a nested theme FileView watcher | `host_quickshell_workspace_theme_contract.py` | session FileView watcher policy changed |
| M33: Add a compact `watchChanges:true` theme binding | `host_quickshell_workspace_theme_contract.py` | session FileView watcher policy changed |

Every row above was red and then restored green (exit 0). M9b is the
flight-generation admission guard: an old callback must not consume a newer
request even when it cannot publish its own rows.

M29 opens and reopens the real page after 91 seconds of simulated shell
uptime, requiring the visible loading label until a reply or the flight's
own deadline. M30 requires signal 9 immediately after hiding; M31 requires
a new signal when disabling a pending read. These signals address the
bridge process; they do not prove descendant process-group cleanup.

Before the whole-file watcher count was added, M32 **stayed green**: the
named-membership check only inspected top-level blocks at fixed indentation.
After adding a whitespace-independent count of every `watchChanges` binding
alongside that membership check, both M32 and M33 were red as shown above
and restored green. No input watcher was added to the accepted membership.

One additional mutation, M9, **stayed green**: removing only the second
`generation === state.networksGeneration` comparison in `finishNetworks`.
The late-answer scenario still passed because hiding had already cleared
`networksPending`, and the flight-generation admission guard still rejected
callbacks belonging to a different runner. The comparison was restored and
the same scenario passed again. This redundant guard's survival is recorded;
M9b independently proved the essential correlation boundary.

The bridge's M10 mutation executed only the inert CLI. Its recorded argv was
`["net", "start", "lab"]`; the contract required exactly
`["--json", "net", "list"]`. No real network action was invoked.

### Source runtime palette previews preserve the separate theme catalogues

Run `python tests/theme_registry_contract.py`. The contract executes the real
`palette-summaries --json` CLI with independent temporary source trees, isolated
HOME/XDG directories and bytecode disabled. Expected rows come from the input
YAML/JSON files, without importing exporter helpers. Existing declarative
registry assertions remain in the same discovered contract.

The following exporter breaks were made separately in a disposable source copy
containing the unchanged contract, tool and its nine input files. The tool was
saved before each break; restoring identical bytes and rerunning the contract
returned exit 0 and both OK lines after every row below. Each red result was
exit 1 with the stated assertion, without a syntax error, timeout, missing tool
or unrelated registry failure. The invalid-final-row fixture runs first so an
incremental printer fails specifically for partial stdout.

For the diagnostics below, **exact rows** means `preview differs from exact
per-preset sources/metadata`; **unexpected stdout** means `refusal leaked
successful stdout`, qualified by the fixture named in the table.

| Mutation | Break in `tools/theme_registry.py` in the disposable copy | Observed red diagnostic |
| --- | --- | --- |
| P1 | After validation, replace Violet's appearance with Green's JSON values while retaining Violet's id. | Exact rows |
| P2 | Change `sorted(options)` to `sorted(options)[1:]`, dropping Blue. | Exact rows |
| P3 | Iterate the union of runtime options and every `themes/*/theme.yml` parent id. | Exact rows when the valid unlisted ready/visible manifest appears |
| P4 | Replace exported declarative metadata with `ready` and `true`, leaving the real manifest unchanged. | Exact rows |
| P5 | Bypass `unique_json`'s duplicate-key guard. | `duplicate JSON blue`: unexpected stdout |
| P6 | Bypass the `palette["name"] == theme_id` guard. | `invalid blue name`: unexpected stdout |
| P7 | Bypass the comparison of all six domain values with `palette.yml`. | `changed blue dom_host`: unexpected stdout |
| P8 | Remove `os.O_NOFOLLOW` from the input open flags. | `external symlink tools/choices/choices.yml`: unexpected stdout |
| P9 | Print `json.dumps(rows[-1])` after each row is appended. | `invalid last row`: unexpected stdout |
| P10 | Bypass `PreviewLoader`'s duplicate-key guard. | `duplicate YAML tools/choices/choices.yml`: unexpected stdout |
| P11 | Bypass the source/generated option-set equality check. | `option disagreement`: unexpected stdout |
| P12 | Make `valid_colour` accept every value. | `invalid last row`: unexpected stdout |
| P13 | Write `preview-cache` under the requested root before reading inputs. | `palette preview wrote to the input tree or HOME/XDG` |
| P14 | Permit YAML aliases in `PreviewLoader.compose_node`. | `recursive YAML alias`: unexpected stdout |
| P15 | Clear `os.O_NOFOLLOW` only when opening descendant directories. | `redirected palette ancestor`: unexpected stdout |
| P16 | Filter unexpected palette keys out before checking the exact key set. | `extra key blue`: unexpected stdout |
| P17 | Bypass the repeated-runtime-id guard in `valid_ids`. | `duplicate generated id`: unexpected stdout |

P18 removed only the explicit read-permission-bit guard. This mutation
**stayed green** (exit 0), as did its restoration: the unprivileged caller's
kernel still refuses mode-0 inputs at `os.open`. The explicit guard is kept so
that even a caller able to bypass those permissions refuses the same input.
That elevated-caller mutation was not run here.

The normal fixture matrix additionally covers every prescribed file missing,
unreadable, malformed, invalidly encoded, non-mapping and externally symlinked;
invalid/duplicate ids, disagreeing options, missing/extra keys, wrong names,
non-string/invalid colours, all six domain values in every preset, invalid
labels/manifests, redirected ancestors and non-regular inputs. Every refusal
requires exit 1, empty stdout and the registry diagnostic prefix without a
traceback. Byte, entry, mode and symlink-target snapshots remain unchanged on
success and refusal, including external targets and HOME/XDG directories.

Positive controls change only Blue's valid appearance colour, change source
labels and valid manifest metadata, reorder generated options, and remove Blue
from both option catalogues along with its palette file. A complete valid
unlisted manifest adds no row; even malformed unlisted input is not read.
Repeated accepted-source runs emit stable bytes and exactly five distinct
source appearances. None of these checks switches an actual theme or proves
installed state, asset rights, browser behavior or hardware acceptance.

#### Parser failures and repository-root anchoring

The same discovered contract now refuses invalid date-shaped YAML values in
all four YAML inputs, 5000-digit JSON integers in every preset, and excessive
JSON/YAML nesting. Each refusal requires exit 1, empty stdout, the registry
prefix without a traceback, and unchanged input/HOME/XDG snapshots. The
original readers failed these new cases with `wrong refusal diagnostic`.
An audit hook around the real CLI entry point counts opens of the resolved
root path; the original per-input opens failed that assertion.

The following separate mutations used saved disposable source copies and the
unchanged contract. Each red was exit 1 with the assertion shown; restoring
the saved input bytes returned exit 0 and both contract OK lines.

| Mutation | Break | Observed red diagnostic |
| --- | --- | --- |
| P19 | Stop converting YAML `ValueError` to `ThemeError`. | `invalid YAML date tools/palette/palette.yml: wrong refusal diagnostic` |
| P20 | Stop converting YAML `RecursionError` to `ThemeError`. | `excessive YAML nesting tools/palette/palette.yml: wrong refusal diagnostic` |
| P21 | Stop converting JSON `ValueError` to `ThemeError`. | `oversized JSON integer blue: wrong refusal diagnostic` |
| P22 | Stop converting JSON `RecursionError` to `ThemeError`. | `excessive JSON nesting blue: wrong refusal diagnostic` |
| P23 | Reopen the resolved root path in each `read_source` call instead of duplicating the shared descriptor. | `preview must open resolved repository root exactly once` |
| P24 | Add Amber to source/generated runtime choices and palette variants, with its own valid JSON, without extending the installer loop. | `legacy runtime presets differ from the installer loop` |

The installer comparison parses the task YAML and the Jinja product list,
then compares that list with the runtime choices classified as legacy by
the palette source. It introduces no additional exporter input or theme list.

P25 changes the row iteration from `options` to `generated_options` after
their required set-equality check. It **stayed green** (exit 0), as did its
restoration: every validated input has the same id set and sorted output
under either iteration. This equivalent mutation is recorded without
weakening the source/generated agreement check. The exporter retains source
options as the requested ids.

### The v1 host target stages the managed lifecycle and drives every apply

`python tests/playbook_topology_contract.py` follows the real imports of
`playbooks/v1-host.yml`. The closure must be `lab.yml`'s, then the
`host_desktop_hyprland` guard and role, then the `host_sleep_guard` guard and
role, each once. Its resolver refuses missing, escaping, absolute, templated,
symlinked, repeated and cyclic imports, duplicate YAML keys and plays it
cannot see into (tasks, or extra keys on an import). A role or file name in a
comment is not in the closure. The Hyprland import must carry exactly
`host_desktop_hyprland_session_lifecycle_enabled: true` as a YAML boolean, and
no other play may set or inherit it. The installed Ansible engine
(`Playbook.load`, `VariableManager.get_vars`, `Templar`) then evaluates the
`when`, loop and arguments of every file-writing task of both roles, with
`ansible_check_mode` false and the fallback palette as the two fixed runtime
results. The Ly catalog, the five Ly discovery lines, both session targets,
the Quickshell unit and its wants link must be staged. The inactive-runtime
and lifecycle-boundary assertions must evaluate true, and the role must hold
no service or command action. The bare `host-desktop-hyprland.yml` import must
fail the same check. `python tests/docs_contract.py` parses the bash blocks of
README's first run and fast path, the playbook map and release section 5 into
argv. All three must run `ansible-playbook -K playbooks/v1-host.yml`, the
first with `--check --diff`.

Each break below was applied to the tracked file from a copy saved outside
the tree. The listed contract exited 1 with the diagnostic shown. Restoring
the copy gave identical bytes and exit 0 (`playbook topology contract: OK (9
tests)` or `documentation contract: OK`). No mutation stayed green.

| Mutation | Break | Observed red diagnostic |
| --- | --- | --- |
| V1 | Remove the Hyprland import from `v1-host.yml`. | closure files `['v1-host.yml', 'lab.yml', 'foundation.yml', 'host-sleep-guard.yml']` |
| V2 | Remove the sleep-guard import. | closure files end at `host-desktop-hyprland.yml` |
| V3 | Remove the lifecycle opt-in `vars`. | scoped vars `'host-desktop-hyprland.yml': None` |
| V4 | Quote the opt-in as `"true"`. | scoped vars hold the string `'true'` |
| V5 | Redirect the managed catalog copy to `/etc/ly/sessions/`. | `managed catalog does not receive hyperlab-hyprland.desktop` (and Sway) |
| V6 | Set Ly `waylandsessions` to `/usr/share/wayland-sessions`. | `Ly discovery is not restricted to the managed catalog` |
| V7 | Point only the second release apply back at `playbooks/lab.yml`. | `release-evidence.md '## 5. Host convergence': release host commands are ...` |
| V8 | Drop the repeated-import refusal in the resolver. | `playbooks/repeat.yml was accepted; expected refusal: imported twice` |
| V9 | Drop the symlink refusal in the resolver. | `playbooks/linked.yml was accepted; expected refusal: redirected by a symlink` |
| V10 | Filter Quickshell out of the managed target coupling loop. | `Quickshell is not coupled to the managed Hyprland target` |
| V11 | Redirect the Sway session target destination. | `session target hyperlab-sway-session.target is not staged` |
| V12 | Add `host_desktop_hyprland_runtime_enabled: true` to the import. | scoped vars carry the extra runtime key |
| V13 | Add `host_desktop_hyprland_manage_ly: true` to the import. | scoped vars carry the extra Ly key |
| V14 | Also set the opt-in on the `lab.yml` import. | scoped vars `'lab.yml': {...: True}` |
| V15 | Point only README's fast-path second apply at `lab.yml`. | `README.md '### Fast path after the first boot': release host commands are ...` |
| V16 | Import `host-sleep-guard.yml` twice. | `ImportRefused: host-sleep-guard.yml: imported twice` |
| V17 | Set the role default `host_desktop_hyprland_runtime_enabled: true`. | `'Keep host Hyprland configuration side-by-side and inactive' would fail: ['not host_desktop_hyprland_runtime_enabled']` |
| V18 | Set the role default `host_desktop_hyprland_preserve_sway_fallback: false`. | both the inactive and the lifecycle-boundary assertions `would fail` |

V12 and V13 are refused first by the exact import variables. V17 and V18
reach only the engine-evaluated assertions. This is a software proof of the
task inputs: no task ran, no file was installed and no session was observed.

## Proposed decision inventory in the ADR index

`python tests/docs_contract.py` is the red check below. It derives the
proposed set from every numbered record's own Status line (`Status:` or
`- Status:`, any letter case), then parses the "Proposed decisions and
their code" section of `docs/adr/README.md` entry by entry. Each break was
made on the real file from a copy in a scratch directory, observed red with
the message shown, then the copy was put back and the contract was green
again (exit 0, `documentation contract: OK`). Line numbers are those of the
index at the commit that added the inventory. The contract proves the
inventory's membership, fields, labels and links, not that an entry's
description is true: that is source review.

| # | Break | Observed red diagnostic |
| --- | --- | --- |
| I1 | Delete the 0052 inventory entry; its numbered navigation link stays. | `proposal inventory omits 0052-host-without-gpu-passthrough.md` |
| I2 | Repeat the 0017 entry after itself. | `proposal inventory lists 0017-shell-machine-creation.md twice` |
| I3 | The 0052 entry heading links the accepted `0037-qemu-process-confinement.md` instead. | `proposal inventory lists 0037-qemu-process-confinement.md, whose Status is not proposed` |
| I4 | Delete the Activation field of 0044. | `proposal inventory entry 0044-measured-boot.md (ADR index line 394) lacks Activation` |
| I5 | Delete the Prerequisites field of 0051. | `proposal inventory entry 0051-disposable-viewer-and-safe-documents.md (ADR index line 514) lacks Prerequisites` |
| I6 | The first 0052 source link becomes `../../roles/hardware_probe/tasks/choose.yml`. | `... (ADR index line 528): source link '../../roles/hardware_probe/tasks/choose.yml' is not an existing file` |
| I7 | The same link becomes `../../../../../../../../etc/hostname`, an existing file outside the checkout. | `... source link '../../../../../../../../etc/hostname' escapes the repository` |
| I8 | 0044's Built label becomes `none` while its Activation stays `opt-in`. | `... (ADR index line 394): Built 'none' and Activation 'opt-in' disagree` |
| I9 | 0018's Activation label becomes `live`. | `... (ADR index line 218): Activation does not open with one of none, default, on request, opt-in, not established and a description` |
| I10 | ADR 0052 loses its `Status: proposed.` line. | `proposal inventory lists 0052-host-without-gpu-passthrough.md, whose Status is not proposed` |

Positive controls, each green (exit 0) on the real files: reword 0019's
Built description; ADR 0052's `Status: proposed.` becomes
`STATUS: PROPOSED.`; ADR 0047's `Status: Proposed.` becomes
`status: proposed.`. A first version of the built-in fixtures used those
exact Status words as edit anchors, so the second and third controls went
red with `fixture anchor 'Status: proposed.' is missing`. The fixtures now
read each record's Status line from the tree and choose their members from
the derived set, so a harmless case change or a later accepted record
changes which entries are exercised, not whether the check runs.

The contract also runs its own fixtures in a temporary copy of `docs/adr`
and of every linked source: the unchanged index, added prose and Status
case changes are accepted; removal, duplication, an accepted record in
place of a member, a removed or repeated Status line, a mismatched number,
a malformed or escaping heading, a removed navigation link, each removed
field, an unknown label, a build with `Source: none`, and missing,
escaping, absolute and documentation source links are refused, each with
its own message. These mutations of the contract itself show the fixtures
bite:

| # | Break in `tests/docs_contract.py` | Observed red diagnostic |
| --- | --- | --- |
| I11 | The loop that refuses an omitted member no longer raises. | `inventory mutation entry removed was accepted` |
| I12 | `DECLARED_STATUS` loses `re.IGNORECASE`. | `0001-image-store-layout.md: unrecognized status line '- Status: accepted for M2 static integration'`, from the real tree before the fixtures run |
| I13 | `source_refusal` no longer returns `escapes the repository`. | `inventory mutation source escaping failed for another reason: ValueError: '<tmp>/outside.py' is not in the subpath of '<tmp>/repo'` |
| I14 | The refusal of an entry whose record is not proposed is deleted. | `inventory mutation accepted record substituted failed for another reason: AssertionError: proposal inventory omits 0054-private-machine-diagnostics.md` |

I13 is red through the contract's own code, not an environment error: with
the guard gone, the next step cannot place the escaping file in the
checkout, and the fixture harness reports any exception other than the
expected refusal as a failure. A first harness let that `ValueError`
escape as a bare traceback; it now names it. A first attempt at I13 edited
the identical lines of `evidence_refusal` instead, stayed green because no
roadmap evidence link escapes, and was repeated on `source_refusal`.

The inventory mutations I1–I14 were repeated with the v1 host-command
checks present in the same entrypoint. All fourteen breaks still exited 1
with the diagnostics above (the index line numbers shifted after the
activation-path clarification); all restorations and the three wording
and case controls exited 0. The v1 command check was also exercised in a
disposable fixture containing the real README, playbook map and release
runbook: changing only the second release apply to `playbooks/lab.yml`
failed with `release-evidence.md '## 5. Host convergence': release host
commands are ...`, showing the wrong third argv. Restoring the saved
runbook bytes passed. The normal `python tests/docs_contract.py` entrypoint
retains both sets of fixtures and checks; neither proof replaces the other.

The inventory fixtures also reject a Decision field saying `accepted`
while its record is still proposed, and a source link into a hidden
directory. The latter points at `.github/workflows/ci.yml`, copied from
the repository into each scratch tree, so a missing file cannot account
for the refusal. An unrecognized Status header immediately below a title
must be refused before a record can be treated as having no Status. The
fixtures replace a member's header with `**Status:** proposed.` or
`Status : proposed` and remove its inventory entry. Before the guard was
added, the first fixture failed with `inventory mutation unrecognized
Status '**Status:** proposed.' was accepted`; after the guard, both forms
are refused with the record's name and `unrecognized status line`.

These additional mutations ran in executable copies of the contract, with
the repository root adjusted only for the copy's directory depth. Each
copy was saved before mutation, ran the normal entrypoint against the
repository and its disposable fixtures, exited 1 as shown, then was
restored from the saved bytes and exited 0 (`documentation contract: OK`).
No mutation stayed green.

| # | Break in `tests/docs_contract.py` | Observed red diagnostic |
| --- | --- | --- |
| I15 | Delete the require that Decision opens with proposed. | `inventory mutation Decision accepted was accepted` |
| I16 | Remove only the hidden-directory condition from `source_refusal`, retaining the docs-directory refusal. | `inventory mutation source is hidden was accepted` |
| I17 | Delete the require that rejects an unrecognized Status header before the no-Status return. | `inventory mutation unrecognized Status '**Status:** proposed.' was accepted` |

### Native Nitro view stays gated, read-only and observational

The deployment contract executes the role's two boolean assertions and the
feature document copy against a disposable destination for both flags and
compares the exact bytes written. The read-only runtime contract executes
the real bridge in a disposable copy with inert tracing `hyperlabctl` and
Nitro clients. The offscreen runtime contract instantiates the real state,
coordinator and Control Center; its Nitro scenarios keep the production
command binding, completion and feature-file handlers with recording
stand-ins for the process and the file, and the real deadline Timer, whose
`running` state is observed and whose triggered signal is emitted without
waiting for the interval. Each source was copied before breaking it,
restored from that copy (byte-identical) and the same predicted check rerun.
No mutation called a real client, broker or hardware node.

| Mutation | Check | Observed red assertion |
| --- | --- | --- |
| N1: Default the Nitro flag on | `host_desktop_common_contract.py` | Nitro feature must default to boolean false |
| N2: Skip the boolean assertion for strings and coerce with `bool` | `host_desktop_common_contract.py` | Nitro nonboolean reached installation: 'false' |
| N3: Enable Nitro from `Boolean(parsed.nitro_view_enabled)` | QML Nitro disabled-page | invalid feature document enabled Nitro |
| N4: Let `validSubpage` admit Nitro unconditionally | QML Nitro disabled-page | disabled direct Nitro navigation succeeded |
| N5: Keep the `hyperlabctl` prerequisite before the Nitro branch | `host_quickshell_readonly_runtime_contract.py` | Nitro status exact read-only argv changed: absent hyperlabctl with a working Nitro client: [] |
| N6: Run `battery off` instead of `status` | `host_quickshell_readonly_runtime_contract.py` | Nitro status exact read-only argv changed: success: [['battery', 'off']] |
| N7: Run `fan 100 100` instead of `status` | `host_quickshell_readonly_runtime_contract.py` | Nitro status exact read-only argv changed: success: [['fan', '100', '100']] |
| N8: Read the limiter without its capability | QML Nitro failures | false battery capability shown as an observation |
| N9: Show the limiter card for any snapshot, absent reading as off | QML Nitro failures | false battery capability shown as an observation |
| N10: Keep the previous RGB readback when `per_zone` is false | QML Nitro failures | RGB readback stayed visible after capability loss |
| N11: Drop the boolean type check of the fan capability | QML Nitro failures | malformed Nitro status accepted |
| N12: Accept any integers as fan percentages | QML Nitro failures | malformed Nitro status accepted |
| N13: Accept non-hex zone colours | QML Nitro failures | malformed Nitro status accepted |
| N14: Remove the 16384-character response bound | QML Nitro failures | malformed Nitro status accepted |
| N15: Do not arm the completion deadline | QML Nitro page/small viewport | Nitro request did not arm its completion deadline |
| N16: Remove the freshness boundary | QML Nitro failures | stale Nitro observation appears current |
| N17: Remove the flight-generation admission guard | QML Nitro late-answer | old Nitro answer consumed the new request |
| N18: Do not signal the bridge on hide | QML Nitro late-answer | Nitro hide did not stop its bridge process |
| N19: Remove the single-flight admission guard | QML Nitro page/small viewport | overlapping Nitro read accepted |

Every row above was red and then restored green. N8 changes state
validation and N9 only presentation; both fail the same visible-content
assertion, which runs before the unsupported case.

One additional mutation, N20, **stayed green**, as its Networks counterpart
M9 did: removing only the second `generation === state.nitroGeneration`
comparison in `finishNitro`. Hiding, disabling and a feature-file reload
already clear `nitroPending`, and N17's admission guard rejects callbacks of
another runner. The comparison was restored and the scenario passed again.

The bridge mutations N6 and N7 executed only the inert client, which
recorded its argv; the contract requires exactly `["status"]` and no
`hyperlabctl` call.

### Capture-session capability, recovery layout and key-sheet repairs

The initial regression checks failed on the previous production code:
stdout-only refusal became "The machine bridge did not answer"; the GTK
GPU rungs differed from the CLI; real GTK allocated Clean at y=18 with
height 154 and Services at y=132 with height 154; the system panel had no
key-sheet entry. A separate real Quickshell failed-start probe produced no
capability answer, while its successful-process control returned JSON.

The capability contract executes real Quickshell processes against inert
executables and production validation. Its disposable copy shortens the
start and completion timers. The GTK contracts execute production AST
builders with real widgets on a private X server, using the production CSS
for allocation. The ladder contract executes the real CLI trust command
and provider with controlled inputs, checks the default and a changed
provider ladder, and inspects the GPU rungs, Networks dock and Create
inspector. The key-sheet contract activates the real panel row offscreen.
No host operation or installed bridge is invoked.

Each source was copied before mutation, restored byte-for-byte afterward,
and its predicted check rerun. Every row below was red and restored green;
none stayed green. Check names below are files in `tests/`.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| L1: Replace the provider ladder with a literal reversed rank map | `recovery_gpu_ladder_contract.py` | recovery GPU ladder differs from CLI |
| L2: Substitute `0` for the Networks dock rank | `recovery_gpu_ladder_contract.py` | clean: recovery rank differs from CLI |
| L3: Substitute `0` for the Create inspector rank | `recovery_gpu_ladder_contract.py` | clean: recovery rank differs from CLI |
| L4: Remove integer and unique-rank validation | `recovery_gpu_ladder_contract.py` | unavailable ladder was replaced by invented ranks |
| L5: Resolve the GPU owner's rung from its network | `recovery_gpu_ladder_contract.py` | GPU owner was ranked by its network instead of its handoff profile |
| N1: Restore the old fixed-coordinate Networks builder | `recovery_network_layout_contract.py` | Networks tiles overlap at 760x560: (24, 18, 336, 154), (24, 132, 336, 154) |
| K1: Remove the system panel's host key sheet row | `system_panel_key_sheet_contract.py` | system panel has no available host key sheet entry |
| B1: Do not arm the capability completion deadline | `machine_capability_transport_contract.py` | capability request never answered |
| B2: Do not arm the failed-start deadline | `machine_capability_transport_contract.py` | missing: known cause lost: The machine bridge timed out while reading capabilities |
| B3: Replace the structured refusal with the generic message | `machine_capability_transport_contract.py` | refused: known cause lost: The machine bridge did not answer |
| B4: Do not spend the capability request | `machine_capability_transport_contract.py` | a duplicate callback changed a spent capability result |
| B5: Discard interrupted exit status | `machine_capability_transport_contract.py` | crash: known cause lost: The machine bridge exited with code -1 |
| B6: Do not signal the retiring capability process | `machine_capability_transport_contract.py` | supersede: retiring probe survived or replaced the new answer (the inert replacement detects the surviving process and exits 9) |
| B7: Do not cancel the runner when capabilities are cleared | `machine_capability_transport_contract.py` | clearing capabilities retained a pending runner |
| P1: Restore the Machine pane's fixed "The machine bridge did not answer" Connect header | `host_quickshell_runtime_contract.py` | capabilities-unavailable: "the Connect header hid the bridge's reported cause" |

B4 first failed through the successful-answer check because the duplicate
failure replaced it; after adding an explicit before/after comparison, the
same mutation failed with the more specific diagnostic shown above. Both
runs restored green. GTK allocation covers requested 760×560, 1000×760 and
500×560 viewports plus substantially taller tile content. This does not
accept compositor placement or focus on hardware. A missing and a
non-executable bridge both report failed start: the Quickshell process
interface does not distinguish their causes for the caller, and the text
names both installation and execute-permission checks instead of guessing.

The existing operation QML contract also retains the production capability
component and its timers, replacing only its process transport. Its earlier
inert object exposed just `running`; the whole verifier caught that fixture
mismatch after deadline ownership was added. The adapted lifecycle scenario
passes without removing or relaxing any assertion.

P1 covers the second place the observed text came from. Even with a
known cause in `ShellState`, `MachineContextPane.qml` printed the fixed
generic sentence as its Connect description whenever capabilities were
unavailable. The runtime contract's `capabilities-unavailable` scenario now
reads that header after a stderr failure and after a stdout-only refusal.

## Recovery GTK display prerequisites

The Networks entrypoint runs the actual allocation worker with a PATH
containing only GTK's bundled `gtk4-broadwayd`, plus invalid inherited X11
and Wayland displays. It must run without an undeclared Xvfb dependency.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| D1: Restore the Xvfb-based `run_gtk_worker` | `recovery_network_layout_contract.py` | Xvfb is required for recovery layout allocation |
| N1 repeated on Broadway: restore the old fixed-coordinate Networks builder | `recovery_network_layout_contract.py` | Networks tiles overlap at 760x560: (24, 18, 336, 154), (24, 132, 336, 154) |
| L1 repeated on Broadway: sort GPU rungs in ascending rank order | `recovery_gpu_ladder_contract.py` | recovery GPU ladder differs from CLI |

All three mutations turned red, then green after restoring the saved
source bytes. The backend change preserves real GTK geometry and provider
parity coverage; missing display tools remain a failure.

## Hosted capability runtime

The real capability transport contract still refuses a missing `qs`. With
the system Quickshell hidden from PATH, the hosted workflow's pinned source
build supplies its own executable. The same build commands were executed
locally, using the installed Qt and a private CLI11 dependency prefix;
Ubuntu package installation and hosted execution remain CI acceptance.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| Q1: Remove `cmake --install` from the fixed toolchain, with a fresh runtime prefix and no system `qs` | workflow version smoke, then `machine_capability_transport_contract.py` | `qs: command not found`, then `real Quickshell is required for capability transport` |
| Q2: Change the archive SHA-256 digest | workflow source-build commands | checksum `FAILED`, before configuration or compilation |

Both were red, restored byte-for-byte, then green. Restoring installation
made the real transport scenarios pass using the privately built `qs`,
with the system runtime still hidden. A changed archive is refused.

## Native GPU ladder parity

`gpu_ladder_parity_contract.py` executes `ShellState.gpuLadder` and
`OwnershipInstrument.rungs` under Qt and parses both Python claim maps
with the AST. All four must agree with the real CLI trust JSON generated
from `gpu_trust_levels`. Native literals remain; their migration to a
shared runtime source is explicitly deferred in proposed ADR 0055.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| G1: Reverse OwnershipInstrument's identities and ranks | `gpu_ladder_parity_contract.py` | `OwnershipInstrument.rungs differs from CLI` |
| G2: Reverse ShellState's rank map | same | `ShellState.gpuLadder differs from CLI` |
| G3: Reverse `render.GPU_LADDER` | same | `render.py: GPU_LADDER differs from CLI` |
| G4: Reverse `focus_accent.GPU_LADDER` | same | `focus_accent.py: GPU_LADDER differs from CLI` |
| G5: Reverse the configured authority without updating native consumers | same | `GPU_LADDER differs from CLI` |

Each source was saved before mutation, restored byte-for-byte, then checked
green. G5 proves configuration drift is caught; the installed native
consumers do not yet update dynamically with the provider.

## Failed-start bridge diagnoses

The real capability transport contract now requires distinct diagnoses
after bounded existence and execute-permission probes. It covers a
missing path, a non-executable file, an executable with a missing
interpreter, and an unavailable inspection executable, in addition to the
previous answer, timeout, interruption and cancellation cases.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| S1: Replace the missing/unreadable-path reason with a combined failed-start sentence | `machine_capability_transport_contract.py` | `missing: known cause lost` |
| S2: Replace the non-executable reason with that sentence | same | `denied: known cause lost` |
| S3: Replace the executable-but-failed reason with that sentence | same | `interpreter: known cause lost` |
| S4: Do not restart the short deadline for path inspection | same | `inspection-missing: known cause lost` (total timeout hid inspection failure) |

All four were red, restored byte-for-byte, then green. The operation QML
harness also substitutes the new child Process type while keeping the
production capability component, timers and assertions intact. These
diagnoses do not identify the original installed Nitro failure. The
stdout-only refusal fixture exercises a defensive path; the shipped bridge
also writes its refusal reason to stderr.

## System-panel key-sheet chord

The panel activation scenario compares its displayed chord with HostKeys'
existing key-sheet entry. `host_key_sheet_contract.py` separately retains
the executed compositor binding and bidirectional sheet parity checks.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| K2: Advertise `SUPER + F2` on the key-sheet row | `system_panel_key_sheet_contract.py` | `system panel advertises a different key-sheet chord than HostKeys` |

The mutation was red, restored byte-for-byte, then green at both viewport
sizes and on both output fixtures. It adds no second shortcut list.

## Product symbol geometry B

`product_symbol_geometry_contract.py` instantiates the real QtQuick Shapes
paths at 16, 24, 32, 33, 48, 64 and 128 units, with `strokeScale` values
0, 0.75, 1, 1.25 and 3. It extracts the renderer's literal scene with the
Python AST, reads its evaluated constants and records its actual drawing
commands. Correct but unused constants therefore cannot conceal drift in
the painted ring or core. Qt 6 is required; a missing runtime fails.

The following constant mutations were each executed separately in
`IsolationGlyph.qml` and `render_isolation_ring.py` (16 mutations). The
geometry contract rejected each with `<glyph|renderer>: <name> must be
<expected>`, then passed after exact restoration.

| Property | Break value (original → mutation) |
| --- | --- |
| `radiusRatio` | `0.46` → `0.47` |
| `arcInnerRatio` | `0.685` → `0.686` |
| `cutRatio` | `0.41` → `0` |
| `ringRadiusRatio` | `0.555` → `0.556` |
| `ringStrokeRatio` | `0.057` → `0.058` |
| `coreRadiusRatio` | `0.413` → `0.414` |
| `smallCoreRadiusRatio` | `0.435` → `0.436` |
| `smallThreshold` | `33` → `34` |

These additional mutations were also red, restored byte-for-byte, then
green (33 total, no green survivors). Unless stated otherwise, the check is
`python tests/product_symbol_geometry_contract.py`.

| Mutation | Observed red result |
| --- | --- |
| Change only the glyph cut from `0.41` to `0.4100001` | `glyph: cutRatio must be 0.41` (constants are compared exactly) |
| Delete `readonly property int smallThreshold: 33` from the glyph | `glyph: smallThreshold must be 33` |
| Change `glyph.size < glyph.smallThreshold` to `<=` | `glyph: small variant at 33` |
| Add `capStyle: ShapePath.RoundCap` to the first arc | `glyph: arcs must be filled without caps` |
| In the first `PathLine`, use `glyph.size / 2 - glyph.innerRadius * glyph.cutRatio` for x | `glyph: a cut is not vertical` |
| Remove `* glyph.strokeScale` from the inner-radius expression | `glyph: a cut is not vertical` |
| Remove the `Math.max(glyph.cutOffset, ...)` inner-radius clamp | `glyph: a cut is not vertical` at extreme thickness |
| Remove `Math.max(1, ...)` from the glyph's ring stroke width | `glyph: strokeScale or one-pixel ring minimum` |
| Set the first arc's `fillColor` to `glyph.core` | `glyph: arcs must be filled without caps` |
| Change the first `sweepAngle: 360` to `180` | `glyph: ring/core circle geometry` |
| Change `fillColor: glyph.core` to `"transparent"` | `glyph: ring/core colour` |
| Change the first `PathArc.Counterclockwise` direction to `Clockwise` | `glyph: annulus arc` |
| Replace the default `core: glyph.stroke` binding with `"white"` | `core must follow stroke by default` |
| In `engravedArc`, replace the recess `ctx.fill()` with `ctx.stroke()` | `renderer: relief must fill both arcs, stroke the ring and fill the core` |
| Keep the renderer's core constant but paint `const core = r * 0.15` | `renderer: painted core path differs` |
| Keep the renderer's ring constant but pass `5 * unit` as the painted ring width | `renderer: painted ring stroke` |
| Change the last pixel's red sample in `isolation-ring-1920x1080.png`, keeping a valid PNG | `host_identity_asset_contract.py`: `identity asset changed without review` |

For example, replay the required source cases from the repository root with
this helper. It saves a copy before each mutation, restores in `finally`,
and checks both red and restored green without Git restoration:

```python
from pathlib import Path
import shutil
import subprocess
import tempfile


def exercise(path, before, after):
    with tempfile.TemporaryDirectory(prefix="symbol-mutation-") as tmp:
        backup = Path(tmp) / path.name
        shutil.copyfile(path, backup)
        source = backup.read_text()
        assert before in source
        try:
            path.write_text(source.replace(before, after, 1))
            red = subprocess.run(
                ["python", "tests/product_symbol_geometry_contract.py"], check=False
            )
        finally:
            path.write_bytes(backup.read_bytes())
        assert red.returncode != 0, "mutation stayed green"
        subprocess.run(
            ["python", "tests/product_symbol_geometry_contract.py"], check=True
        )


glyph = Path("roles/host_desktop_common/files/quickshell/hyperlab/IsolationGlyph.qml")
renderer = Path("tools/wallpaper/render_isolation_ring.py")
exercise(glyph, "cutRatio: 0.41", "cutRatio: 0")
exercise(glyph, "    readonly property int smallThreshold: 33\n", "")
exercise(renderer, "ringRadiusRatio: 0.555", "ringRadiusRatio: 0.556")
```

The pixel mutation used the existing non-interlaced 8-bit PNG's final
scanline and final pixel's filtered red byte, incremented modulo 256. No
later red sample depends on that byte, so only that pixel's red channel
changes. Recompressing IDAT and recalculating its CRC preserves a valid PNG;
`python tests/host_identity_asset_contract.py` must reject it. Restore the
saved PNG and require the same command to pass.

## Generated trust pool v3

`trust_pool_v3_generated_contract.py` regenerates all twelve PNGs and their
manifest with Qt's software rasteriser, compares exact bytes and checks the
printed hashes. Its material probe samples the evaluated geometry B scene
and reads real PNG pixels for HOST and DEV in both variants. It checks
sphere clipping, neutral HOST, grey arc/ring material, dark gaps and both
placements. Its AST/source check permits only pixel-buffer painting and
refuses text/font primitives and palette colour literals. Its input fixtures
exercise missing domains, duplicate mappings, invalid colours, missing files
and symlink redirection. Host and guest source paths are parsed as YAML.

For the stage checks below, import the contract and call the named function.
This is the same code that the full contract runs, without repeating twelve
renders for a source, input or deployment failure:

```python
import importlib.util
from pathlib import Path
import tempfile


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load(Path("tests/trust_pool_v3_generated_contract.py"), "v3_contract")
contract.source_contract()                  # source stage
contract.deployment_contract()              # deployment stage
renderer = load(contract.RENDERER, "v3_renderer")
with tempfile.TemporaryDirectory(prefix="trust-pool-mutation-") as temporary:
    directory = Path(temporary)
    contract.input_contract(renderer, directory)       # input stage
    contract.material_contract(renderer, directory)    # material stage
```

Save copies before each mutation and restore them byte-for-byte afterward.
The checks below were red, then green after restoration. The full generated
contract was rerun after restoring V3-01, V3-02 and V3-17; the same named
stage was rerun for each other source mutation. V3-03 uses
`python tests/trust_wallpaper_engine_contract.py` for both runs.

| Mutation | Check | Observed red result |
| --- | --- | --- |
| V3-01: insert `ctx.fillText("bad", 0, 0)` before painting | full generated contract | `text or reticle primitive in renderer` |
| V3-02: change palette `dom_dev` from `#5b8cff` to `#5b8cfe` without regenerating | full generated contract | `palette/manifest drift: dev` |
| V3-03: set v3 `wallpaper_may_set_trust: true` | engine contract | `trust authority boundary changed` |
| V3-04: add `ctx.moveTo(0, 0); ctx.lineTo(100, 0)` | source | `unexpected Canvas drawing operations` |
| V3-05: assign `ctx.font = "12px sans-serif"` | source | `text or reticle primitive in renderer` |
| V3-06: add an unused `"#5b8cff"` literal to the renderer | source | `hardcoded identity colour: dev` |
| V3-07: change `cutRatio` from `0.41` to `0.42` | material | `geometry B ratios` |
| V3-08: disable the HOST desaturation branch | material | `capture differs from material: host/01` |
| V3-09: replace the sphere's clipped coverage with `1` | material | `capture differs from material: host/01` |
| V3-10: move variant 02 from 75% to 70% of image width | material | `capture differs from material: host/02` |
| V3-11: disable duplicate-key rejection in the YAML loader | input | `accepted duplicate domain` |
| V3-12: check only the palette file's symlink flag, omitting its parents | input | `accepted redirected palette directory` |
| V3-13: revert the guest asset source to v2 | deployment | `guest deploys old pool` |
| V3-14: revert the host wallpaper copy source to v2 | deployment | `host deploys old pool` |
| V3-15: revert the theme asset set to v2 | deployment | `v3 not selected: themes/trust-model/theme.yml` |
| V3-16: omit the explicit dirty rectangle from `putImageData`, then render HOST 01 | material | `capture differs from material: host/01` |
| V3-17: alter the last pixel of LAB 02, preserving a valid PNG, and update its manifest digest | full generated contract | `generated output drift: images/lab/02.png` |
| V3-18: add an unused Python `[91, 140, 255]` colour triple | source | `hardcoded identity RGB: dev` |
| V3-19: replace palette-derived DEV tint with a used Python `0x5b8cff` packed value | full generated contract | `hardcoded packed identity RGB: dev` |
| V3-20: override DEV tint with a used QML `0x5b8cff` packed value | full generated contract | `hardcoded packed identity RGB: dev` |
| V3-21: repeat packed values for all six identities in Python and QML using nine numeric spellings (108 cases) | source | `hardcoded packed identity RGB: <identity>` in every case |

V3-16 saves and restores both the renderer and the captured PNG. With Qt
6.11.2 the shortened call produced a blank capture despite correct material
samples, so this case checks the actual saved image.

V3-17 decompresses IDAT, increments the last scanline's final pixel's filtered
red byte modulo 256, recompresses IDAT and recalculates its CRC. Updating the
manifest hash deliberately makes a hash-only check insufficient: only the
comparison against freshly generated output detects the changed artwork.
Both the PNG and manifest are restored before the green run.

V3-19 replaces the renderer's palette-to-tint list comprehension with:

```python
packed = 0x5b8cff if identity == "dev" else int(colour[1:], 16)
tint = [(packed >> shift) & 255 for shift in (16, 8, 0)]
```

V3-20 separates `tint` from the shader closure's combined `width`, `height`
and `quiet` declaration, then substitutes this QML expression for `art.tint`:

```javascript
const packed = 0x5b8cff;
const tint = art.tint[0] === (packed >> 16)
    ? [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255]
    : art.tint;
```

Both used-constant mutations initially survived the full contract: twelve
exact renders, material samples, palette inputs and deployment checks all
stayed green. The duplicated value still matched the current palette. With
numeric literal checking, both fail before rendering; restoring each returns
the source stage to green. The complete contract passes after restoration.

V3-21 uses each domain's packed value in both substitutions. The nine forms
are hexadecimal, uppercase hexadecimal, decimal, octal, binary, decimal with
digit separators, hexadecimal with digit separators, integral decimal with
`.0`, and exponential notation. All 108 source-stage checks were red, and all
108 restored checks were green. Python values come from the AST; numeric
tokens in QML strings are converted to values before comparison with the
palette. These cases check literal refusal without requiring Qt to execute
every spelling.

### Trust pool runtime, negative space and product geometry

These cases exercise `tests/trust_pool_v3_generated_contract.py`; source and
material stages from V3-01 through V3-21 remain in place. Save the renderer,
product renderer, every affected PNG and `manifest.yml` before each case,
then restore their saved bytes after it. Recompression is an explicit green
control, not an undisclosed surviving artwork mutation. ADR 0057 explains
why compressed-byte equality across runtimes was the wrong requirement.

| ID | Break or control | Check | Observed result |
| --- | --- | --- | --- |
| V3-22 | Decode `images/lab/02.png`, encode the identical RGB scanlines with filter 0 and zlib level 0, update only its manifest SHA-256 | complete generated contract | old check red (`generated output drift`); corrected check green |
| V3-23 | As V3-22, increment the final pixel's red channel by one, encode with zlib level 1, update its manifest SHA-256 | complete generated contract | red: `generated pixel drift: images/lab/02.png`; restored complete check green |
| V3-24 | Insert the arithmetic mark below in `pixel()`, then regenerate the entire versioned pool | complete generated contract | old check green; corrected check red: `non-ground pixel in geometry gap`, `(39, 30)`; restored check green |
| V3-25 | Insert the gap mark below at each of `position = 0.46`, `0.63`, `0.9`; render HOST/01 to a temporary PNG | `png_pixels`, `ground_offsets`, `ground_contract` | three red refusals at `(835, 612)`, `(835, 665)`, `(835, 749)`; each restored check green |
| V3-26 | Change only product renderer `cutRatio: 0.41` to `cutRatio: 0.42` | complete generated contract | old check green; corrected check red: `pool geometry differs from product symbol`; restored geometry and complete check green |
| V3-27 | Append `changed` to `images/lab/02.png` without updating its manifest hash | `pool_manifest` | red: `manifest hash mismatch`; restored hash check green |
| V3-28 | Re-encode the original RGB values as RGBA, set only the final alpha to 254 and update the manifest hash | `png_pixels` | red: `nonopaque capture`; restored opacity check green |
| V3-29 | In temporary copies, corrupt an IDAT CRC, duplicate IEND, truncate IEND or truncate an IDAT payload | `png_pixels` | four red refusals: `invalid PNG CRC`, `invalid PNG structure`, `truncated PNG chunk`, `truncated PNG payload`; each restored decoder green |
| V3-30 | Copy the pool, change only rotation `interval_minutes: 30` to `31`, keep all image hashes correct | compare both `pool_manifest` results | red: `generated manifest policy drift`; restored policy comparison green |

For V3-22/V3-23, reuse `png_pixels(path)` to obtain the entire RGB buffer.
Build each scanline as a zero filter byte followed by `1672 * 3` RGB bytes;
compress their concatenation with `zlib.compress(scanlines, level)`. Write
PNG signature, IHDR (`1672, 941, 8, 2, 0, 0, 0`), IDAT and IEND, computing
each chunk's CRC over its type and payload. For V3-23 increment `rgb[-3]`
modulo 256 before encoding. Replace the original file's SHA-256 with the
new digest in the saved manifest. V3-22 additionally checks normalization
from the committed opaque RGBA format to RGB: all decoded values must agree.
The original red compression control kept RGBA and its existing filters while
changing only zlib compression. The corrected green control additionally
changes to RGB and filter 0. The committed captures exercise PNG filters 1–4;
this control exercises 0.

V3-24 inserts this at the start of `function pixel(x, y) {`:

```javascript
if (x > 30 && x < 90 && Math.abs(y - 40) < 1
        || y > 30 && y < 90 && Math.abs(x - 40) < 1)
    return [200, 200, 200];
```

Run `python3 tools/wallpaper/render_trust_pool.py` before the contract so
all hashes and temporary renders would agree. It must still reject the
mark, which uses no forbidden keyword or extra Canvas call. The full-image
check rejects it before spending time on another regeneration.

V3-25 instead inserts, with one numeric `position` substituted per case:

```javascript
if (Math.abs(x - centreX) < 1
        && Math.abs(y - centreY - radius * position) < 1)
    return [200, 200, 200];
```

Use the renderer's `render()` with the palette's HOST colour, identity
`host`, variant `01` and a temporary output. Decode it with `png_pixels()`
and call `ground_contract(pixels, ground_offsets("01", geometry_contract()),
path)`. These coordinates cover core/ring space, ring/arc space and the
vertical arc cut. Restore the renderer and check the original HOST/01 PNG
after each refusal. V3-28 uses IHDR colour type 6 with 255 alpha everywhere
except the final pixel, while keeping all RGB values identical.

The complete corrected contract also passed with Arch Qt 6.11.2 and Ubuntu
26.04 Qt 6.10.2 packages in an unprivileged Ubuntu Base runtime restricted
to two CPUs. Exact pixels matched for all twelve images. Twelve renders took
79.7 s and 78.8 s respectively; the Ubuntu contract took 111.92 s overall.
The regeneration budget is 600 s, retaining the renderer's 120 s per-image
limit. This evidence does not establish a hosted workflow or hardware gate.

V3-29 changes only the first IDAT chunk's final CRC byte by XOR with 1;
appends a second valid empty IEND chunk; removes the final IEND CRC byte;
or truncates after three of an IDAT chunk's four CRC bytes. Each starts
from its own copied valid PNG and restores it before the green decode.
V3-30 compares the copied and original pools through `pool_manifest`, with
`require(original == copied, "generated manifest policy drift")`, then
restores the saved manifest and requires equality. These temporary-copy
fixtures leave the versioned pool untouched.

## Native product and lock wallpapers with shared v3 materials

ADR 0058 supersedes the wallpaper relief treatment in ADR 0056. The glyph
path checks above remain intact. Wallpaper-only relief command mutations
are replaced by executed native shader masks and saved-pixel checks; the
shared helper now owns the five full-form geometry ratios. Pool source
mutations target that helper where the literal scene formerly lived in
`render_trust_pool.py`. No pool geometry, policy, hash or pixel tolerance
was broadened.

Before extraction, the extended source and identity contracts both failed
with `shared v3 material missing`. After extraction, all twelve pool
renders remained pixel-exact against the unchanged committed images.
The product contract checks all eight native renders, independent pinned
hashes, negative space and every fully covered neutral core pixel. Product
material probes cover all four sizes and both variants, vertical cuts,
circular gaps and captured pixels. Source checks cover the shared helper
and both entry points.

Each mutation below was applied after copying the changed file, rejected
by the named check, restored byte-for-byte and observed green on that same
check. Stage checks are the same functions called by the complete contracts;
they avoid regenerating all native outputs for a source or configuration
failure. The full contracts run again after restoration through verification.
There were 18 red mutations and no surviving broken invariant. P-19 is an
explicit green compression control.

| Mutation | Check | Observed result |
| --- | --- | --- |
| P-01: add `ctx.fillText("bad", 0, 0)` to shared `draw` | pool `source_contract()` | red: `text or reticle primitive in renderer`; restored green |
| P-02: add a `ctx.fillText` expression string in the product entry point | pool `source_contract()` | red: `text or reticle primitive in renderer`; restored green |
| P-03: add a `ctx.fillText` expression string in the pool entry point | pool `source_contract()` | red: `text or reticle primitive in renderer`; restored green |
| P-04: add `ctx.stroke()` to shared `draw` | pool `source_contract()` | red: `unexpected Canvas drawing operations`; restored green |
| P-05: add a `reticle` declaration in shared `draw` | pool `source_contract()` | red: `text or reticle primitive in renderer`; restored green |
| P-06: change product neutral RGB from `(147, 147, 147)` to `(147, 159, 147)` | product executed material probe, `check_renderer` at 1920×1080 | red: `renderer: neutral sphere is tinted`; restored green |
| P-07: disable the pool HOST desaturation branch | pool `material_contract()` | red: `capture differs from material: host/01`; restored green |
| P-08: change shared `cutRatio` from `0.41` to `0.42` | product material probe | red: `renderer: cutRatio must be 0.41`; restored green |
| P-09: change shared `ringRadiusRatio` from `0.555` to `0.556` | product material probe | red: `renderer: ringRadiusRatio must be 0.555`; restored green |
| P-10: change shared `coreRadiusRatio` from `0.413` to `0.414` | product material probe | red: `renderer: coreRadiusRatio must be 0.413`; restored green |
| P-11: map the product 1920×1080 filename to `(1672, 941)` | identity `configuration_contract()` | red: `native output sizes changed`; restored green |
| P-12: replace shared native canvas width with `1672` | product material probe | red: `renderer: mark scale or centre changed`; restored green |
| P-13: remove lock attenuation by changing `0.55` to `1.0` | lock material probe | red: `renderer: lock material attenuation`; restored green |
| P-14: keep output dimensions but pass `(1672, 941)` to the product's shared scene builder | identity `configuration_contract()` | red: `product bypasses shared v3 drawing`; restored green |
| P-15: replace the shared ground's coordinate grain with `Math.random()` | pool `source_contract()` | red: `non-deterministic material input`; restored green |
| P-16: change the last pixel of a copied native product PNG to `(12, 15, 20)`, with valid chunks and CRCs | identity `capture_contract()` against the unchanged original | red: `native generated pixel drift`; restored green |
| P-17: add a grey `(90, 90, 90)` corner pixel at `(2, 2)` in a copied native product PNG | `ground_contract()` with native dimensions and product placement | red: `non-ground pixel in geometry gap`; restored green |
| P-18: tint the copied native product's interior core pixel at `(998, 518)` to `(80, 82, 80)` | identity `neutral_core_contract()` | red: `neutral sphere is tinted`; restored green |
| P-19: encode the original native pixels as opaque RGB with unfiltered scanlines and new compression | identity `capture_contract()` | green: identical decoded pixels, ground and neutral core |

To replay the source stages, import the listed contract with `tests/` and
`tools/wallpaper/` on `sys.path`. For product/lock material stages, load the
production `scene((1920, 1080), variant, output)`, remove its `onPaint`
capture handler, append `RENDERER_CHECK` and execute it with the contract's
`run`; pass its record to `check_renderer`. This is the identical inspection
used for each native size in `main`. Save and restore the source around
one mutation at a time.

P-16 through P-19 use a copied original PNG. Decode its RGB with
`png_pixels(path, (1920, 1080))`, change only the specified pixel, then encode
a complete non-interlaced eight-bit RGB PNG with filter-zero scanlines and
valid CRCs. Restore from the saved copy before checking green. P-16 passes
the original and copied paths to `capture_contract`; P-17 supplies product
placement `(0.52, 0.48, 0.23)` to `ground_offsets`; P-18 passes diameter
`0.46` to `neutral_core_contract`. These fixtures leave committed images
untouched. SHA pinning remains a separate earlier gate in the full identity
contract; the native pixel stages do not depend on a stale hash to detect
artwork changes.

### Lossless native PNG file budget

The two original 4K material captures were 6,930,410 and 6,929,379 bytes.
The new identity size stage failed on the product 4K capture before the
encoding repair. It checks the 5 MiB ceiling independently for committed
assets and every freshly generated PNG. Hash pinning, native dimensions
and exact decoded RGB comparisons remain unchanged.

Qt's shared capture now supplies temporary eight-bit RGB PPM to the product
entry point. That entry point writes unfiltered RGB PNG with zlib level 9;
the pool still uses its original PNG path. The configuration stage intercepts
the shared capture, supplies known RGB pixels and checks the actual encoded
PNG. It also supplies wrong dimensions, a missing byte and an extra byte:
all must be refused before encoding. Before implementation, that stage
failed with `invalid PNG capture` because the old wrapper did not encode RGB.

| Mutation | Check | Observed result |
| --- | --- | --- |
| P-20: insert a valid `tEXt` chunk with 5 MiB of padding before `IEND` in a copied native PNG; retain every pixel and a valid CRC | identity `file_budget_contract()`; independently decode and compare the unchanged RGB | red: `identity PNG exceeds 5 MiB`; restored green |
| P-21: remove the native PPM header and payload-length refusal from the product renderer | identity `configuration_contract()` with invalid RGB captures | red: `product accepted invalid native RGB capture`; restored green |

Both mutated files were copied before modification and restored from their
saved copies. P-20 uses a copy of the 1920×1080 product PNG; build the padding
as PNG `tEXt` type plus `padding\0`, 5 MiB of `x` bytes and its CRC, preceded
by the four-byte payload length. P-21 removes only the condition and its
`unexpected native RGB capture` exception, leaving capture and encoding in
place. No check, size ceiling or pixel requirement is weakened.

## Product display name

`tests/product_display_name_contract.py` tokenizes QML string literals,
executes every discovered CLI help parser and the version banner, parses
Ansible deployment data, records real notification argv, and executes the
production name binding with Quickshell's real read-only process transport. The existing
Qt offscreen harness evaluates the bar, desktop, byline, key-sheet heading
and all five workspace titles at desktop and narrow sizes. Compositor
fixtures execute the real owner-bound focus selector on both backends.
No real compositor, notification service or host action is contacted.

For an individual stage, run from the repository root:

```python
import sys
sys.path.insert(0, "tests")
import product_display_name_contract as contract

contract.qml_strings()                 # QML string tokens, including escapes
contract.cli_contract()                # real parser tree and input refusals
contract.deployment_contract()         # parsed role and config data
contract.docs_contract("Sfere")
contract.notification_contract("Sfere")
contract.reader_contract()             # shared byte/path table, Python and Bash
contract.native_name_contract("Sfere")  # real byte transport, no host observations
contract.shell_contract("Sfere")        # evaluated presentation
contract.focus_contract()               # owner-bound compositor fixtures
```

Save the affected file before each source mutation and restore its exact
bytes afterward. Every red case below was executed separately, then the
same stage passed after restoration. PD-19 is an intentional green control:
a valid new shared value must reach every runtime consumer. Twenty-three broken
invariants were red; no unexpected green survivor occurred.

| ID | Mutation | Stage | Observed result |
| --- | --- | --- | --- |
| PD-01 | Replace the bar's `IdentityMark` text binding with `"HyperLab"` | QML | red: old product display string |
| PD-02 | Put `"HYPERLAB"` in the idle desktop label | QML | red: old product display string |
| PD-03 | Put `"Hyperlab · Control Center"` in a workspace title | QML | red: old product display string |
| PD-04 | Put `"HyperLab"` in the nested key-sheet group data | QML | red: old product display string |
| PD-05 | Hardcode `"Sfere"` in the bar instead of its shared binding | QML | red: product name duplicated outside shared input |
| PD-06 | Return ordinary argparse help without shared product formatting | CLI | red: CLI help uses old product name |
| PD-07 | Remove the product name from the version banner | CLI | red: CLI version banner drift |
| PD-08 | Change parser `prog` to `sferectl` | CLI | red: CLI command name changed |
| PD-09 | Change the configured Quickshell directory name to `sfere` | deployment | red: Quickshell config name changed |
| PD-10 | Change the rail namespace to `sfere-bar` | deployment | red: internal namespace changed |
| PD-11 | Hardcode notification `--app-name` as `HyperLab` | notification | red: wrong notification app name |
| PD-12 | Disable the CLI's file and parent symlink rejection | CLI | red: accepted redirected input |
| PD-13 | Replace strict shell parsing with ordinary JSON parsing and last-key-wins behavior | native name | red: duplicate name published as `B` instead of withheld |
| PD-14 | Restore the old product name in the README heading | docs | red: product heading missing |
| PD-15 | Change the shared byline to `by Someone` | shell | red: product byline drift |
| PD-16 | Put `"\u0048yperLab"` in the bar text | QML | red: decoded old product display string |
| PD-17 | Supply `Sfere` as the shell's invalid-input fallback | native name | red: invalid input published a default identity |
| PD-18 | Change the role's product source to a missing file | deployment | red: shared name not deployed exactly once |
| PD-19 | Change only the canonical name to `Example Name` | CLI, native name, shell, notification, focus | green control: all consumers use the changed value; restored green |
| PD-20 | Restore `HyperLab · ` as the adapter's focus prefix | focus | red: neither backend can focus the renamed workspace |
| PD-21 | Remove the notification banner-format guard | notification | red: notification defaulted after an invalid name read |
| PD-22 | Remove the key-sheet name binding in the launcher | shell | red: key-sheet name binding missing |
| PD-23 | Bypass the keyboard notification helper with a direct old-name notification | notification | red: old notification product string |
| PD-24 | Install the product input after the QML source instead of before it | deployment | red: product input installed after its consumers |

The complete product contract passed after restoring all source mutations.
Input fixtures also refuse missing, unreadable, malformed, duplicate and
redirected CLI input, missing/malformed/duplicate native input, and failed
or malformed CLI banners before notification or focus dispatch in that
initial implementation. The revised deployed-file cases below replace the
banner transport; PD-15 then referred to the QML-local byline. The physical Nitro and Predator presentation gates remain separate.


### Shared deployed identity and presentation regressions

The deployed file now carries both `name` and `byline`. Focus and notification
helpers validate it directly; CLI banners use only their own checkout. The
old PD-21 banner-guard mutation is superseded by PD-40's input-guard mutation.
The byline change that was rejected by PD-15 is now a valid shared-input
control (PD-41); consumer drift is rejected by PD-32. ADR 0059 explains the
narrow installed-session documentation exception and the deferred visible
surfaces, which remain open in the release roadmap.

Each case below was run separately against the revised contract, with exact
source bytes saved before mutation and restored before the green run. All
eighteen negative mutation cases were red and all restorations green. The two
valid shared-value changes stayed green across their listed consumers.

| ID | Mutation | Stage | Observed result |
| --- | --- | --- | --- |
| PD-25 | Read focus identity from `hyperlabctl --version` again | focus | red: stale CLI cannot select the owner's window on either backend; restored green |
| PD-26 | Read theme notification identity from the CLI banner again | notification | red: wrong application name with a stale CLI; restored green |
| PD-27 | Return 1 when the keyboard notification is withheld | operation | red: saved layout incorrectly reports failure; restored green |
| PD-28 | Return 1 when the theme notification is withheld | operation | red: successful theme body incorrectly reports failure; restored green |
| PD-29 | Return 1 after restoring the fallback bar when its notification is withheld | operation | red: restored fallback incorrectly reports failure; restored green |
| PD-30 | Load product identity during CLI module import | CLI entry point | red: missing product input escapes the normal exit-2 refusal boundary; restored green |
| PD-31 | Add an unlisted old-name command help literal | AST help source | red: new old-name help source; restored green |
| PD-32 | Hardcode the QML byline while changing only the shared byline | native FileView and shell | red: native byline differs from the shared input; restored green |
| PD-33 | Add a desktop label containing `"Hyper" + "Lab"` | QML tokens, then shell | tokens green as expected; evaluated desktop scan red; restored green |
| PD-34 | Split the old name in the bar's `Accessible.name` | QML tokens, then shell | tokens green as expected; evaluated accessibility scan red; restored green |
| PD-35 | Split the old name in the launcher's `Accessible.name` | QML tokens, then shell | tokens green as expected; evaluated accessibility scan red; restored green |
| PD-36 | Replace the README's installed session names with generic names | docs | red: README does not name installed sessions; restored green |
| PD-37 | Mark the remaining visible-surface migration complete | deferred inventory | red: visible migration is not open; restored green |
| PD-38 | Change a desktop entry's `Name=` without updating its inventory | parsed desktop entries | red: undocumented session name; restored green |
| PD-39 | Change the Waybar drawer tooltip without updating its inventory | parsed JSONC | red: undocumented fallback brand/tooltip; restored green |
| PD-40 | Bypass the notification reader's document-pattern guard | notification | red: invalid product input causes a notification; restored green |
| PD-41 | Change only the canonical byline to `by Example` | CLI, native FileView, shell, notification, focus | green control: all consumers accept the shared byline; restored green |
| PD-42 | Change only the canonical name to `Example Name` | CLI, native FileView, shell, notification, focus | green control: all consumers use the changed value; restored green |
| PD-43 | Bypass the keyboard helper with a direct old-name notification | notification source and argv | red: old notification product string; restored green |
| PD-44 | Remove the deployed reader's symlink refusal | notification | red: redirected name accepted; restored green |

The notification fixtures cover stale, failing and unavailable CLI stubs plus
missing, nonregular, redirected, malformed and duplicate product documents.
They also reject overlong bylines, NUL bytes and extra document lines. The
operation fixtures execute the real keyboard script and the real theme and
fallback-bar function bodies with inert actuation. No notification is sent
when the name is missing, stderr reports it, and completed operations succeed.
The CLI fixture runs the actual entry point against missing, malformed and
redirected product inputs and requires exit 2, `hyperlabctl:` and no traceback.

### Display-only CLI input and complete deferral inventory

Identity is now loaded only by help/version presentation. The copied real
entry point must run `panic status` against an empty isolated runtime directory
with missing, malformed, duplicate, accented or symlinked identity input.
For each input, root help, nested panic help and version must still refuse
with exit 2, the usual diagnostic and no traceback. No emergency stop is
engaged and no live runtime state is read by these fixtures.

The deferred-surface check requires every inventoried file in ADR 0059 and
specifically in the open roadmap item. An AST scan inventories old-name
`Refused(...)` literals from the machine-action bridge. The Bash-reader
stage compares all four extracted `product_name()` bodies and exercises
parent-directory symlink refusal for each. Notification fixtures also refuse
a redirected parent before dispatch.

Each case below was backed up, mutated, checked red, restored byte-for-byte
and checked green. All seven negative cases failed as predicted; PD-49 was
checked independently through both structure and notification behavior.

| ID | Mutation | Stage | Observed result |
| --- | --- | --- | --- |
| PD-45 | Remove `privatestack-operation.py` from the open roadmap item | deferred inventory | red: operation surface omitted from open roadmap item; restored green |
| PD-46 | Remove one old-name bridge refusal from ADR 0059 | AST refusal inventory | red: bridge refusal omitted from ADR inventory; restored green |
| PD-47 | Read identity in `build_parser()` again | CLI entry point | red: missing display input blocks emergency-stop status dispatch; restored green |
| PD-48 | Change one character in the Waybar reader's document pattern | Bash reader equality | red: product readers differ; restored green |
| PD-49 | Replace the theme reader's parent loop with leaf-only symlink refusal | Bash equality and notification argv | both red: reader drift and notification accepts redirected parent; both restored green |
| PD-50 | Make the same leaf-only change in all four Bash readers | Bash parent refusal | equality stays green as expected, runtime refusal red: adapter reader accepts redirected parent; restored green |
| PD-51 | Add an unlisted old-name `Refused(...)` literal to the machine bridge | AST refusal inventory | red: new old-name bridge refusal outside inventory; restored green |

The display-only behavior supersedes the previous whole-parser refusal;
ADR 0059 explains why emergency stop cannot depend on cosmetic identity.

### Shared reader edges and known deferred surfaces

One byte/path fixture table now drives the CLI reader, all four Bash readers
and the native Quickshell bridge transport. It includes valid LF, CRLF and
no-newline documents, a changed identity, accented words, lone CR, extra lines,
NUL, duplicate/missing/null/long fields, redirected leaves and parents,
nonregular files, missing paths and zero-mode files. Bash runs every case in
C and each installed UTF-8 locale. The native fixture also withholds valid
output from a failed bridge and handles a missing bridge. The fixed adapter
route also runs with an invalid compositor backend and refuses extra arguments.
Document-mode output must preserve the exact validated bytes.

The deferred inventory is known at `233b046`, not exhaustive. Its contract
now checks the host lock template, shell-action stderr, provisioning, Gaming
Mode, session failure and guest lock/Ly files. It parses lock label blocks,
the guest task YAML and the guest lock-label function; an AST scan checks all
five old-name shell-action stderr prefixes.

Each target below was copied before mutation, restored byte-for-byte, and its
stage rerun green. PD-01 was repeated: restoring the old bar label was red.
PD-62 intentionally records a surviving mutation under the unprivileged test
identity; it is not evidence of a root-runtime refusal.

| ID | Mutation | Stage | Observed result |
| --- | --- | --- | --- |
| PD-52 | Remove `hyprlock.conf.j2` from the open roadmap item | deferred inventory | red: lock surface omitted; restored green |
| PD-53 | Remove `privatestack-shell-actions.py` from the open roadmap item | deferred inventory | red: shell-action surface omitted; restored green |
| PD-54 | Add an unlisted old-name `print(..., file=sys.stderr)` to the shell-action bridge | AST stderr inventory | red: new old-name shell stderr outside inventory; restored green |
| PD-55 | Change the deferred host lock subtitle | parsed lock labels | red: host lock labels changed without updating inventory; restored green |
| PD-56 | Change a guest lock-label fallback | guest function AST | red: guest lock labels changed without updating inventory; restored green |
| PD-57 | Change guest Ly `initial_info_text` | parsed task YAML | red: guest Ly text changed without updating inventory; restored green |
| PD-58 | Restore Python universal-newline translation | shared reader table | red: CLI accepts lone CR; restored green |
| PD-59 | Remove the function-local C locale from all four Bash readers | shared reader table | reader equality green as expected; runtime red: accented name accepted under `en_US.utf8`; restored green |
| PD-60 | Remove the adapter identity reader's parent/leaf symlink guard | native shared table | red: redirected identity published; restored green |
| PD-61 | Publish the native child buffer regardless of exit status | native failed-child fixture | red: failed transport published an identity; restored green |
| PD-62 | Remove the explicit readable-mode guard from all four Bash readers | shared reader table, equality and native bridge | green: this user's kernel read still refuses the zero-mode file; restored green; root-runtime behavior not established |
| PD-63 | Add a newline to document-mode output in all four readers | shared document bytes | red: validated identity bytes changed; restored green |
| PD-64 | Detect the compositor before the fixed identity route | native bridge with invalid backend | red: valid identity unavailable without a compositor; restored green |
| PD-65 | Remove the fixed identity route's argument-count guard | real adapter argv | red: caller-supplied path accepted; restored green |

The native bridge cases execute the real adapter while the existing
provenance restrictions remain unchanged. PD-62 kept both reader
equality and every unprivileged refusal case green, because kernel permission
checks still deny the zero-mode document to this user.

### Host login, guest presentation and locale coverage

The deferred inventory baseline is now `db7c99b`. The contract scans both
host and guest QML recursively, with exactly one existing guest idle fallback
pinned to its original file. It parses host Ly defaults and all repository
desktop sources (including the guest template), requiring complete inventory
coverage and exact Name/Comment values. Shell printf formats and the root
Gaming Mode parser description are pinned, as are their documentation entries.

The previous reader fixture passed with locale discovery limited to
C/C.utf8/POSIX. It now refuses that environment and requires a non-C UTF-8
locale whose unguarded Bash ranges actually accept the accented control.
PD-59 was repeated: identical readers without their local C setting still
pass the equality check, but reject parity under `en_US.utf8` by accepting
the accented input. No root execution is claimed: PD-62 remains the recorded
normal-user survivor, and ADR 0059 labels the stronger behavior intended and
unverified.

Each file was copied before mutation and restored byte-for-byte; the extra
desktop source was copied from a saved fixture and removed after the check.
Locale discovery and control mutations use inert executables in a temporary
PATH. All restored stages were green.

| ID | Mutation | Stage | Observed result |
| --- | --- | --- | --- |
| PD-66 | Remove `roles/host_desktop_sway/defaults/main.yml` from the open roadmap item | deferred inventory | red: host login surface omitted; restored green |
| PD-67 | Add `text: "HyperLab"` to guest `UiText.qml` | recursive QML strings | red: old product display string; restored green |
| PD-68 | Copy the allowed `HYPERLAB WORKSTATION` label into guest `UiText.qml` | scoped QML exception | red: old product display string outside its pinned file; restored green |
| PD-69 | Change host Ly `box_title` | parsed defaults YAML | red: deferred host Ly gate text changed; restored green |
| PD-70 | Change the guest desktop template's Name | parsed desktop entries | red: undocumented greeter/application name or comment; restored green |
| PD-71 | Change the guest desktop template's Comment | parsed desktop entries | red: undocumented greeter/application name or comment; restored green |
| PD-72 | Add an unlisted desktop source | desktop inventory coverage | red: inventory differs from repository sources; restored green |
| PD-73 | Change the keyboard compositor-rejection printf format | parsed shell tokens | red: deferred helper printf changed; restored green |
| PD-74 | Change the root Gaming Mode argparse description | parser AST | red: deferred root Gaming Mode help changed; restored green |
| PD-75 | Change the guest NVIDIA readiness printf format | parsed shell tokens | red: deferred helper printf changed; restored green |
| PD-76 | Limit locale discovery to C/C.utf8/POSIX | shared reader table prerequisites | red: non-C UTF-8 locale required; restored green |
| PD-77 | Replace the pinned guest idle fallback | recursive QML strings | red: deferred QML label changed; restored green |
| PD-78 | Remove the guest desktop QML input | QML input coverage | red: host/guest presentation input missing; restored green |
| PD-79 | Discover a language locale but make its unguarded Bash control refuse the accented word | widening control | red: installed language locales do not exercise Bash range widening; restored green |
