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
why the effective value is asserted in a play. The red message is the
one the contract prints.

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
  setting". The playbook stays green: the host variable wins over the
  group one, so only the contract sees it.
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
- Restore: copy the broken file back from the intact tree; the contract
  prints "Public repository process hygiene contract: OK" and the three
  playbook runs pass again.
