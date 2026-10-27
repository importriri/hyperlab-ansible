# Third-party licences and file origins

This is a record of evidence, not legal advice and not a publication
permission. It accounts for every file tracked in this repository and for
every software source the playbooks and roles name by default, and it says
what a future ISO or other image would have to settle first. Where the
evidence does not settle a question, the entry stays unresolved: its
provenance or permission is pending, and nothing unresolved is approved for
bundling or for any distribution beyond what already exists.

- Input commit: `9def5390653b95967fe7143c6195bf1ed0004609` (1302 tracked
  paths).
- Package records, upstream licence files, pinned sources and generator
  re-runs: 2026-10-27.
- Machine-readable file inventory: [`file-inventory.tsv`](file-inventory.tsv).
- The `arch-bootstrap` repository has its own audit; the
  `arch-hypervisor-lab` repository is not covered here.

Four questions are kept apart:

1. **This repository's files** ([section 1](#1-repository-files)): what is
   tracked here, where each file comes from and under which terms.
2. **What the playbooks install or fetch** ([sections 2 to
   6](#2-packages-installed-from-the-arch-linux-repositories)): software
   downloaded on a target at apply time. The repository contains none of it.
3. **What is built from pinned upstream source** ([section
   3](#3-pinned-upstream-sources-built-on-a-target)), with the patches this
   repository applies to it.
4. **What a future image could carry** ([section
   8](#8-distribution-modes)): an image that contains a component *is* a
   redistribution of it. The dispositions are inputs to that design; they
   are not the design, and the ISO release gate stays open.

## 1. Repository files

[`file-inventory.tsv`](file-inventory.tsv) has a header and one row per path
of `git ls-files -z` at the input commit, dotfiles, binary images, tests and
generated files included. Its columns:

| Column | Meaning |
| --- | --- |
| `path` | the tracked path |
| `sha256` | digest of the file's bytes at the input commit |
| `kind` | `code`, `test`, `doc`, `config`, `template`, `patch`, `raster-image`, `vector-image` or `legal` |
| `origin` | `first-party declaration`, `produced by a tracked script`, `derived from a named upstream` or `unknown` |
| `relationship` | what the file is copied, generated or derived from, or a statement recorded about it; `none` when nothing is known beyond the origin |
| `evidence` | the introducing commit and what was checked |
| `licence` | the terms that apply as far as the evidence goes, or `unresolved` |
| `status` | `declared`, `documented` or `unresolved` |

The digests are those of the input commit. The commit that adds the
inventory changes one of those files, `README.md` (a link to this report);
every other tracked file is byte-identical to the input commit. The two
audit files are listed here instead of in the inventory, which cannot hold
its own digest:

- `docs/third-party-licences.md` (this report);
- `docs/file-inventory.tsv` (the inventory).

### What each origin rests on

- **`first-party declaration`** (status `declared`). The root
  [`LICENSE`](../LICENSE) and [`AUTHORS.md`](../AUTHORS.md) state that the
  repository is the maintainer's work under MIT. For these rows the content
  was searched for third-party copyright lines, licence notices, `SPDX`
  identifiers and phrases such as "adapted from" or "copied from", and none
  that names another source was found. That is the whole basis: a statement
  by the maintainer and the absence of contrary evidence. It is not an
  independent proof, and confirming it stays with the maintainer.
- **`produced by a tracked script`** (status `documented`). A script in the
  repository produces the file from tracked inputs, and re-running it into a
  temporary directory on 2026-10-27 produced byte-identical output. The
  shipped files were not overwritten. The terms are those of the script and
  its inputs, which are themselves `declared`.
- **`derived from a named upstream`** (status `documented`). The upstream,
  its revision and its licence were read at the source on 2026-10-27.
- **`unknown`** (status `unresolved`, licence `unresolved`). No source,
  generator, author or licence record exists in the repository or its
  history. These files are tracked publicly today; that does not settle
  their provenance or grant any permission.

Git history gives the commit that first added a path (renames are followed,
copies are not), its date and the identity on that commit. It is not proof
of authorship: a commit records who added bytes, not who wrote them or where
they came from. An image manifest's hash or its `canonical` and `candidate`
flags record which bytes are meant; they are not a rights record either.

### Result

| Kind | Rows | Origin | Status |
| --- | ---: | --- | --- |
| `code` | 256 | first-party declaration | declared |
| `test` | 258 | first-party declaration | declared |
| `doc` | 239 | first-party declaration | declared |
| `doc` | 1 | generated (`docs/choices.html`) | documented |
| `config` | 322 | first-party declaration | declared |
| `config` | 44 | generated (palette fragments, trust-model renders, `group_vars/all/choices.yml`) | documented |
| `template` | 52 | first-party declaration | declared |
| `vector-image` | 7 | first-party declaration | declared |
| `raster-image` | 12 | generated (`tools/wallpaper/`) | documented |
| `raster-image` | 105 | unknown | **unresolved** |
| `patch` | 4 | derived from a named upstream (GPL-2.0-or-later) | documented |
| `legal` | 1 (`AUTHORS.md`) | first-party declaration | declared |
| `legal` | 1 (`LICENSE`) | derived from a named upstream (SPDX MIT text) | documented |
| **Total** | **1302** | | 1135 declared, 62 documented, 105 unresolved |

`LICENSE` is the MIT License text of the
[SPDX licence list](https://spdx.org/licenses/MIT.html) (version 3.29.0) with
its copyright line filled in: after whitespace normalisation the text from
"Permission is hereby granted" to the end is identical.

### Generated files and their generators

| Files | Generator and inputs | Re-run on 2026-10-27 |
| --- | --- | --- |
| `roles/host_desktop_common/files/wallpapers/isolation-ring-*.png` (8) | `tools/wallpaper/render_isolation_ring.py` | byte-identical with Qt 6.11.2 `qmlscene` (software rasteriser) |
| `roles/host_desktop_common/files/wallpapers/contained-planes-*.png` (4) | `tools/wallpaper/render_contained_planes.py` | byte-identical with Qt 6.11.2 `qmlscene` |
| `roles/host_desktop_sway/files/palette/{green,violet,blue,red}/*` (32) | `tools/palette/render_palette.py <variant>` from `tools/palette/palette.yml` | byte-identical |
| `themes/trust-model/rendered/*` (10) and `themes/trust-model/preview.html` | `tools/theme_render.py trust-model --preview` | byte-identical |
| `docs/choices.html` | `tools/choices/choices.py panel` from `tools/choices/choices.yml` | byte-identical |
| `group_vars/all/choices.yml` | `tools/choices/choices.py vars` | byte-identical |

The wallpaper scripts draw geometry with Qt Quick; the output is only as
stable as the Qt release, which is why the version is recorded.

### Patches of upstream source

Four tracked files are patches of third-party source. Their terms are those
of the upstream files they modify, **not** the root MIT licence. Each was
applied with `patch --dry-run -p1` to the pinned upstream file fetched on
2026-10-27, and each applied cleanly.

| Patch | Upstream file and pin | Terms |
| --- | --- | --- |
| `roles/looking_glass/files/client-captured-button-press.patch` | `client/src/app.c`, [gnif/LookingGlass](https://github.com/gnif/LookingGlass) `0140a3f6fb616c5636d6c430eb71b8a7d5338e39` | GPL-2.0-or-later (upstream file header) |
| `roles/guest_looking_glass_linux/files/portal-compat-runtime.patch` | `host/platform/Linux/capture/pipewire/src/portal.c`, same pin | GPL-2.0-or-later; the patch replaces the whole file and carries the upstream copyright and licence notice |
| `roles/guest_looking_glass_linux/files/pipewire-thread-loop-runtime.patch` | `host/platform/Linux/capture/pipewire/src/pipewire.c`, same pin | GPL-2.0-or-later; as above |
| `roles/nitro_sense/files/an515-55-four-zone.patch` | `src/linuwu_sense.c`, [0x7375646F/Linuwu-Sense](https://github.com/0x7375646F/Linuwu-Sense) `73a25ec243a44ba2b1703e8d0a76fa2735062506` | GPL-2.0-or-later (the file's `SPDX-License-Identifier`; the project's `LICENSE` is GPL-3.0) |

Two statements elsewhere in the repository are narrower than this evidence:

- the root `README.md` and `LICENSE` name MIT without an exception for these
  four files (S3 below);
- [`nitro-sense.md`](nitro-sense.md) says the repository "does not vendor
  Linuwu-Sense source" and that the module builds "under upstream's GPL-3.0
  license". The tracked patch contains upstream context lines, and the file
  it changes declares GPL-2.0-or-later (acer-wmi lineage) inside a project
  licensed GPL-3.0.

### Statements and palettes recorded in the relationship column

- **Catppuccin palette.** `tools/hyperlabctl/hyperlabctl/panel/ui.py` names
  ten Catppuccin Mocha colours with their values;
  `roles/host_desktop_sway/files/mako.conf` and
  `roles/host_desktop_sway/files/starship.toml` use Mocha colour values. All
  ten values in `ui.py` equal those of
  [catppuccin/palette](https://github.com/catppuccin/palette) at
  `07d02aa110ef9eb7e7427afca5c73ba9cf7f8ebd` (MIT). The notice is given in
  [section 9](#9-third-party-notices).
- **"Written from scratch."** The commit that added the Rofi launcher and
  power menu, the themed swaylock, the GTK settings and the power-menu
  helper states that their layout was inspired by GPL-3.0 reference dotfiles,
  written from scratch, and that nothing was copied. Seven current text
  files descend from files added in that commit and their rows carry the
  statement (`wallpaper.png`, added by the same commit, is an unresolved
  image below). Files the commit only modified (`sway.config`, `waybar.css`,
  `waybar.jsonc`) are not marked. It is a first-party statement; the
  reference dotfiles were not identified or compared.
- **Quickshell test stand-ins.** The 26 files under
  `tests/quickshell_stubs/Quickshell/` imitate part of the Quickshell QML
  API (Quickshell itself is LGPL-3.0-only) so the shell can be instantiated
  offscreen. They are fixture-driven declarations; reading them found no
  upstream source text.
- **SVG files.** The seven SVG files under `roles/host_desktop_sway/files/`
  are short hand-written markup (16 to 37 lines) without editor metadata,
  embedded raster data or a notice. Their design origin rests on the
  first-party declaration like the code.

No font file, icon theme or third-party theme is tracked. Fonts, icons and
themes reach a system only as packages ([section 5](#5-fonts-icons-and-themes)).

### Images without provenance

105 raster images have no recorded origin. They stay `unresolved`: the root
MIT licence is a general declaration and does not establish the origin of
these assets or relicense anything that came from elsewhere. Neither their
appearance, their file names, the commit identity nor the presence or
absence of metadata is used as evidence of rights here.

| Pool | Files | Recorded facts | Installed by |
| --- | ---: | --- | --- |
| `themes/assets/hyperlab-symbols-v1/images/` | 10 | added in `53489ee`; listed with hashes in its `manifest.yml` (`status: canonical`); each file carries an embedded provenance-metadata chunk (`caBX`), whose claims this report neither reproduces nor relies on | no role; read by `tools/theme_render.py` for `themes/trust-model/preview.html` and offered by `tools/theme_assets.py` |
| `themes/assets/hyperlab-trust-v2/images/<identity>/` | 12 | added in `53489ee`; listed in its `manifest.yml` (`status: candidate`); each carries the same kind of embedded chunk | `host_desktop_sway` (all 12, host default); `guest_desktop_hyprland` (the profile wallpaper) |
| `roles/host_desktop_sway/files/wallpapers/{blue,green,red,violet}/` | 80 | added in `c22ffca`; palette-indexed PNG without text or provenance chunks; no generator in the repository or its history | `host_desktop_sway` (all 80, host default) |
| `roles/host_desktop_sway/files/wallpaper-desktop.png`, `wallpaper-lockscreen.png` | 2 | added in `c22ffca`; no text or provenance chunks; no generator | `host_desktop_sway` (host default) |
| `roles/host_desktop_sway/files/wallpaper.png` | 1 | added in `aafcbb6` as a role backdrop; no text or provenance chunks; no generator | no task at the input commit |

The exact paths and digests are the `unresolved` rows of the inventory.

## 2. Packages installed from the Arch Linux repositories

The roles install Arch packages with `community.general.pacman` (or
`ansible.builtin.package` in `guest` and `guest_safe_documents`) and pin no
version. Arch Linux is a rolling distribution: an apply installs whatever the
enabled mirrors serve that day. The versions below are those of the official
package records (`core`, `extra`, `multilib`) on 2026-10-27, read from the
JSON search API (`https://archlinux.org/packages/search/json/?name=<name>`).
The licence column copies the record; the record names the package's own
licence and does not inventory everything it embeds. The dependency closure
of these packages was not resolved: it is an explicit requirement of any
later image build (S7).

Classes:

- **H** host default: `playbooks/lab.yml` (`foundation.yml` plus
  `host_desktop_common`, `host_desktop_sway` and `looking_glass`);
- **M** host, on a Machine operation: `guest` (create and reset) and
  `workbench` (seal and derive);
- **O** optional host bricks with their own playbooks:
  `host_desktop_hyprland`, `host_audit`, `host_usbguard`, `qemu_apparmor`,
  `measured_boot`, `nitro_sense` (its out-of-tree build is disabled by
  default) and `service_exposure`;
- **G** inside workstation guests: `workstation_kernel`,
  `guest_desktop_hyprland` (and its `gaming-clean` and `gaming-dirty`
  profiles, which enable `multilib`), `dev_ide`, `guest_gpu_nvidia`,
  `guest_gaming_telemetry`, `guest_looking_glass_linux` (an opt-in flag that
  the VFIO guest playbooks set) and `guest_safe_documents`.

The `{{ kernel_name }}-headers` entry of `looking_glass` resolves to
`linux-hardened-headers` with the default `kernel_name`;
`guest_looking_glass_linux` picks the headers of the running guest kernel
(`linux-zen-headers` under `workstation_kernel`). Lists that only remove
packages (`host_desktop_sway_removed_packages`,
`guest_desktop_hyprland_legacy_packages` and the stock-kernel fallback of
`workstation_kernel`) install nothing and are not listed.

| Package | Repo and version | Arch record licence | Class | Installed by |
| --- | --- | --- | --- | --- |
| [alsa-utils](https://archlinux.org/packages/extra/x86_64/alsa-utils/) | extra 1.2.16-1 | GPL-2.0-or-later | HG | host_desktop_sway, guest_desktop_hyprland |
| [bat](https://archlinux.org/packages/extra/x86_64/bat/) | extra 0.26.1-3 | Apache-2.0 OR MIT | H | host_desktop_sway |
| [binutils](https://archlinux.org/packages/core/x86_64/binutils/) | core 2.47-4 | FSFAP; GFDL-1.3; GPL-2.0-or-later; GPL-3.0-or-later; LGPL-2.0-or-later; LGPL-3.0-or-later | H | looking_glass |
| [brightnessctl](https://archlinux.org/packages/extra/x86_64/brightnessctl/) | extra 0.5.1-3 | MIT | H | host_desktop_sway |
| [btop](https://archlinux.org/packages/extra/x86_64/btop/) | extra 1.4.7-1 | Apache-2.0 | H | host_desktop_sway |
| [celluloid](https://archlinux.org/packages/extra/x86_64/celluloid/) | extra 0.30-2 | GPL-3.0-or-later | H | host_desktop_sway |
| [cmake](https://archlinux.org/packages/extra/x86_64/cmake/) | extra 4.4.4-1 | BSD-3-Clause | HG | looking_glass, guest_looking_glass_linux |
| [dkms](https://archlinux.org/packages/extra/any/dkms/) | extra 3.4.4-1 | GPL-2.0-or-later | HOG | looking_glass, nitro_sense, guest_looking_glass_linux |
| [dnsmasq](https://archlinux.org/packages/extra/x86_64/dnsmasq/) | extra 2.93-1 | GPL-2.0-or-later | H | kvm_host |
| [edk2-ovmf](https://archlinux.org/packages/extra/any/edk2-ovmf/) | extra 202608-1 | Apache-2.0; BSD-2-Clause-Patent; MIT | H | kvm_host |
| [eza](https://archlinux.org/packages/extra/x86_64/eza/) | extra 0.23.5-2 | EUPL-1.2 | H | host_desktop_sway |
| [fd](https://archlinux.org/packages/extra/x86_64/fd/) | extra 10.5.0-3 | MIT OR Apache-2.0 | H | host_desktop_sway |
| [ffmpeg](https://archlinux.org/packages/extra/x86_64/ffmpeg/) | extra 9.0.2-2 | GPL-3.0-only | H | host_desktop_sway |
| [ffmpegthumbnailer](https://archlinux.org/packages/extra/x86_64/ffmpegthumbnailer/) | extra 2.3.1-1 | GPL-2.0-or-later | H | host_desktop_sway |
| [file-roller](https://archlinux.org/packages/extra/x86_64/file-roller/) | extra 44.7-1 | GPL-2.0-or-later | HG | host_desktop_sway, guest_desktop_hyprland |
| [fontconfig](https://archlinux.org/packages/extra/x86_64/fontconfig/) | extra 2.18.3-2 | HPND AND Unicode-DFS-2016 | H | looking_glass |
| [foot](https://archlinux.org/packages/extra/x86_64/foot/) | extra 1.28.0-2 | MIT | H | host_desktop_sway |
| [fzf](https://archlinux.org/packages/extra/x86_64/fzf/) | extra 0.74.5-1 | MIT | H | host_desktop_sway |
| [gcc](https://archlinux.org/packages/core/x86_64/gcc/) | core 16.2.1+r23+gd564253eb6c8-1 | GFDL-1.3-or-later; GPL-3.0-or-later WITH GCC-exception-3.1 | HOG | looking_glass, nitro_sense, guest_looking_glass_linux |
| [git](https://archlinux.org/packages/extra/x86_64/git/) | extra 2.56.0-1 | GPL-2.0-only | HMOG | looking_glass, workbench, nitro_sense, dev_ide, guest_looking_glass_linux |
| [gmp](https://archlinux.org/packages/core/x86_64/gmp/) | core 6.3.0-3 | GPL-2.0-or-later; LGPL-3.0-or-later | H | looking_glass |
| [grim](https://archlinux.org/packages/extra/x86_64/grim/) | extra 1.5.0-2 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [gst-libav](https://archlinux.org/packages/extra/x86_64/gst-libav/) | extra 1.28.8-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [gst-plugin-pipewire](https://archlinux.org/packages/extra/x86_64/gst-plugin-pipewire/) | extra 1.6.10-1 | MIT | H | host_desktop_sway |
| [gst-plugins-bad](https://archlinux.org/packages/extra/x86_64/gst-plugins-bad/) | extra 1.28.8-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [gst-plugins-base](https://archlinux.org/packages/extra/x86_64/gst-plugins-base/) | extra 1.28.8-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [gst-plugins-good](https://archlinux.org/packages/extra/x86_64/gst-plugins-good/) | extra 1.28.8-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [gst-plugins-ugly](https://archlinux.org/packages/extra/x86_64/gst-plugins-ugly/) | extra 1.28.8-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [gtk4](https://archlinux.org/packages/extra/x86_64/gtk4/) | extra 4.24.1-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [gtk4-layer-shell](https://archlinux.org/packages/extra/x86_64/gtk4-layer-shell/) | extra 1.3.0-1 | MIT | H | host_desktop_sway |
| [gvfs](https://archlinux.org/packages/extra/x86_64/gvfs/) | extra 1.62.0-3 | LGPL-2.0-only | HG | host_desktop_sway, guest_desktop_hyprland |
| [gvfs-mtp](https://archlinux.org/packages/extra/x86_64/gvfs-mtp/) | extra 1.62.0-3 | LGPL-2.0-only | H | host_desktop_sway |
| [gvfs-nfs](https://archlinux.org/packages/extra/x86_64/gvfs-nfs/) | extra 1.62.0-3 | LGPL-2.0-only | H | host_desktop_sway |
| [gvfs-smb](https://archlinux.org/packages/extra/x86_64/gvfs-smb/) | extra 1.62.0-3 | LGPL-2.0-only | H | host_desktop_sway |
| [intel-media-driver](https://archlinux.org/packages/extra/x86_64/intel-media-driver/) | extra 26.3.5-1 | BSD-3-Clause; MIT | H | host_desktop_sway |
| `iptables-nft` | no package of that name; core [iptables](https://archlinux.org/packages/core/x86_64/iptables/) 1.8.13-1 provides and replaces it | GPL-2.0-only (`iptables`) | H | kvm_host |
| [jq](https://archlinux.org/packages/extra/x86_64/jq/) | extra 1.8.2-1 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [libdecor](https://archlinux.org/packages/extra/x86_64/libdecor/) | extra 0.2.5-1 | MIT | H | looking_glass |
| [libglvnd](https://archlinux.org/packages/extra/x86_64/libglvnd/) | extra 1.7.0-3 | custom:BSD-like | H | looking_glass |
| [libsamplerate](https://archlinux.org/packages/extra/x86_64/libsamplerate/) | extra 0.2.2-3 | BSD | H | looking_glass |
| [libva-utils](https://archlinux.org/packages/extra/x86_64/libva-utils/) | extra 2.24.0-1 | custom | H | host_desktop_sway |
| [libvirt](https://archlinux.org/packages/extra/x86_64/libvirt/) | extra 12.8.0-1 | GPL-3.0-or-later; LGPL-2.1-or-later | H | kvm_host |
| [libvirt-python](https://archlinux.org/packages/extra/x86_64/libvirt-python/) | extra 12.8.0-1 | LGPL-2.1-or-later | H | network_domains |
| [libxkbcommon](https://archlinux.org/packages/extra/x86_64/libxkbcommon/) | extra 1.13.2-1 | MIT | H | looking_glass |
| [linux-hardened-headers](https://archlinux.org/packages/extra/x86_64/linux-hardened-headers/) | extra 7.2.10.hardened1-3 | GPL-2.0-only | HO | looking_glass, nitro_sense |
| [ly](https://archlinux.org/packages/extra/x86_64/ly/) | extra 1.4.1-1 | WTFPL | HG | host_desktop_sway, guest_desktop_hyprland |
| [make](https://archlinux.org/packages/core/x86_64/make/) | core 4.4.1-3 | GPL3 | HOG | looking_glass, nitro_sense, guest_looking_glass_linux |
| [mako](https://archlinux.org/packages/extra/x86_64/mako/) | extra 1.11.0-1 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [mesa](https://archlinux.org/packages/extra/x86_64/mesa/) | extra 26.2.5-1 | MIT AND BSD-3-Clause AND SGI-B-2.0 | H | host_desktop_sway, looking_glass |
| [mpv](https://archlinux.org/packages/extra/x86_64/mpv/) | extra 0.41.0-6 | GPL-2.0-or-later AND LGPL-2.1-or-later | H | host_desktop_sway |
| [nemo](https://archlinux.org/packages/extra/x86_64/nemo/) | extra 6.6.4-1 | GPL-3.0-or-later AND LGPL-2.1-or-later | H | host_desktop_sway |
| [nettle](https://archlinux.org/packages/core/x86_64/nettle/) | core 4.0-1 | LGPL-3.0-or-later OR GPL-2.0-or-later | H | looking_glass |
| [nftables](https://archlinux.org/packages/extra/x86_64/nftables/) | extra 1.1.7-3 | GPL-2.0-only | HO | lab_isolation, service_exposure |
| [noto-fonts](https://archlinux.org/packages/extra/any/noto-fonts/) | extra 2026.10.01-1 | OFL-1.1-no-RFN | HG | host_desktop_sway, guest_desktop_hyprland |
| [pamixer](https://archlinux.org/packages/extra/x86_64/pamixer/) | extra 1.6-4 | GPL-3.0-or-later | HG | host_desktop_sway, guest_desktop_hyprland |
| [papirus-icon-theme](https://archlinux.org/packages/extra/any/papirus-icon-theme/) | extra 20260801-1 | GPL-3.0 | HG | host_desktop_sway, guest_desktop_hyprland |
| [pavucontrol](https://archlinux.org/packages/extra/x86_64/pavucontrol/) | extra 6.2-2 | GPL-2.0-or-later | H | host_desktop_sway |
| [pciutils](https://archlinux.org/packages/core/x86_64/pciutils/) | core 3.15.0-1 | GPL-2.0-only | HG | hardware_probe, guest_gpu_nvidia |
| [pipewire](https://archlinux.org/packages/extra/x86_64/pipewire/) | extra 1.6.10-1 | LGPL-2.1-or-later; MIT | HG | host_desktop_sway, looking_glass, guest_desktop_hyprland |
| [pipewire-alsa](https://archlinux.org/packages/extra/x86_64/pipewire-alsa/) | extra 1.6.10-1 | MIT | H | host_desktop_sway |
| [pipewire-audio](https://archlinux.org/packages/extra/x86_64/pipewire-audio/) | extra 1.6.10-1 | MIT | H | host_desktop_sway |
| [pipewire-pulse](https://archlinux.org/packages/extra/x86_64/pipewire-pulse/) | extra 1.6.10-1 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [pkgconf](https://archlinux.org/packages/core/x86_64/pkgconf/) | core 3.0.10-1 | ISC | HG | looking_glass, guest_looking_glass_linux |
| [playerctl](https://archlinux.org/packages/extra/x86_64/playerctl/) | extra 2.4.1-5 | LGPL-3.0-only | HG | host_desktop_sway, guest_desktop_hyprland |
| [polkit](https://archlinux.org/packages/extra/x86_64/polkit/) | extra 128-1 | LGPL-2.0-or-later | H | host_desktop_sway |
| [python-gobject](https://archlinux.org/packages/extra/x86_64/python-gobject/) | extra 3.58.1-1 | LGPL-2.1-or-later | H | host_desktop_sway |
| [python-lxml](https://archlinux.org/packages/extra/x86_64/python-lxml/) | extra 6.1.3_1-1 | BSD-3-Clause; GPL-2.0-only; LicenseRef-RNG2Schtrn; LicenseRef-XSD2Schtrn; MIT; MIT-CMU | H | network_domains |
| [qemu-base](https://archlinux.org/packages/extra/x86_64/qemu-base/) | extra 11.1.2-1 | BSD-2-Clause; BSD-2-Clause-Patent; BSD-3-Clause; CC0-1.0; FSFAP; GPL-1.0-or-later; GPL-2.0-only; GPL-2.0-only WITH Linux-syscall-note; GPL-2.0-only WITH Linux-syscall-note OR BSD-2-Clause; GPL-2.0-only WITH Linux-syscall-note OR BSD-3-Clause; GPL-2.0-or-later; GPL-2.0-or-later OR BSD-3-Clause; GPL-2.0-or-later WITH Linux-syscall-note; ISC; LGPL-2.0-or-later; LGPL-2.1-only OR BSD-3-Clause; LGPL-2.1-or-later; LicenseRef-Public-Domain; MIT | H | kvm_host |
| [quickshell](https://archlinux.org/packages/extra/x86_64/quickshell/) | extra 0.3.2-1 | LGPL-3.0-only | HG | host_desktop_common, guest_desktop_hyprland |
| [ripgrep](https://archlinux.org/packages/extra/x86_64/ripgrep/) | extra 15.2.0-1 | MIT OR Unlicense | H | host_desktop_sway |
| [rofi](https://archlinux.org/packages/extra/x86_64/rofi/) | extra 2.0.0-1 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [rtkit](https://archlinux.org/packages/extra/x86_64/rtkit/) | extra 0.14-2 | GPL-3.0-or-later AND MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [slurp](https://archlinux.org/packages/extra/x86_64/slurp/) | extra 1.5.0-2 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [spice-protocol](https://archlinux.org/packages/extra/any/spice-protocol/) | extra 0.14.5-1 | BSD-3-Clause | H | looking_glass |
| [starship](https://archlinux.org/packages/extra/x86_64/starship/) | extra 1.27.0-1 | ISC | H | host_desktop_sway |
| [sway](https://archlinux.org/packages/extra/x86_64/sway/) | extra 1.12-4 | MIT | H | host_desktop_sway |
| [swaybg](https://archlinux.org/packages/extra/x86_64/swaybg/) | extra 1.2.2-1 | MIT | H | host_desktop_sway |
| [swayidle](https://archlinux.org/packages/extra/x86_64/swayidle/) | extra 1.9.1-1 | MIT | H | host_desktop_sway |
| [swaylock](https://archlinux.org/packages/extra/x86_64/swaylock/) | extra 1.8.6-1 | MIT | H | host_desktop_sway |
| [swtpm](https://archlinux.org/packages/extra/x86_64/swtpm/) | extra 0.10.2-1 | BSD-3-Clause | HM | kvm_host, guest |
| [ttf-dejavu](https://archlinux.org/packages/extra/any/ttf-dejavu/) | extra 2.37+18+g9b5d1b2f-8 | custom | H | looking_glass |
| [ttf-jetbrains-mono-nerd](https://archlinux.org/packages/extra/any/ttf-jetbrains-mono-nerd/) | extra 3.5.1-2 | OFL-1.1-no-RFN | HG | host_desktop_sway, guest_desktop_hyprland |
| [udisks2](https://archlinux.org/packages/extra/x86_64/udisks2/) | extra 2.11.2-1 | GPL-2.0-or-later; LGPL-2.0-or-later | H | host_desktop_sway |
| [virt-viewer](https://archlinux.org/packages/extra/x86_64/virt-viewer/) | extra 11.0-4 | GPL | H | host_desktop_sway |
| [vulkan-intel](https://archlinux.org/packages/extra/x86_64/vulkan-intel/) | extra 26.2.5-1 | MIT AND BSD-3-Clause AND SGI-B-2.0 | H | host_desktop_sway |
| [vulkan-tools](https://archlinux.org/packages/extra/x86_64/vulkan-tools/) | extra 1.4.363.0-1 | Apache-2.0 | H | host_desktop_sway |
| [waybar](https://archlinux.org/packages/extra/x86_64/waybar/) | extra 0.15.0-3 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [wayland](https://archlinux.org/packages/extra/x86_64/wayland/) | extra 1.26.0-1 | MIT | H | looking_glass |
| [wayland-protocols](https://archlinux.org/packages/extra/any/wayland-protocols/) | extra 1.49-1 | MIT | H | looking_glass |
| [wayland-utils](https://archlinux.org/packages/extra/x86_64/wayland-utils/) | extra 1.3.0-1 | MIT | H | host_desktop_sway |
| [wireplumber](https://archlinux.org/packages/extra/x86_64/wireplumber/) | extra 0.5.18-1 | MIT | HG | host_desktop_sway, guest_desktop_hyprland |
| [wl-clipboard](https://archlinux.org/packages/extra/x86_64/wl-clipboard/) | extra 2.3.0-1 | GPL-3.0-or-later | HG | host_desktop_sway, guest_desktop_hyprland |
| [xdg-desktop-portal-gtk](https://archlinux.org/packages/extra/x86_64/xdg-desktop-portal-gtk/) | extra 1.15.3-2 | LGPL-2.0-or-later | HOG | host_desktop_sway, host_desktop_hyprland, guest_desktop_hyprland |
| [xdg-desktop-portal-wlr](https://archlinux.org/packages/extra/x86_64/xdg-desktop-portal-wlr/) | extra 0.8.4-1 | MIT | H | host_desktop_sway |
| [xdg-user-dirs](https://archlinux.org/packages/extra/x86_64/xdg-user-dirs/) | extra 0.20-1 | GPL-2.0-or-later | H | host_desktop_sway |
| [zoxide](https://archlinux.org/packages/extra/x86_64/zoxide/) | extra 0.10.0-1 | MIT | H | host_desktop_sway |
| [cloud-image-utils](https://archlinux.org/packages/extra/any/cloud-image-utils/) | extra 0.34-1 | GPL-3.0-only | M | guest |
| [guestfs-tools](https://archlinux.org/packages/extra/x86_64/guestfs-tools/) | extra 1.56.1-1 | GPL-2.0-or-later; LGPL-2.1-or-later | M | workbench |
| [qemu-audio-spice](https://archlinux.org/packages/extra/x86_64/qemu-audio-spice/) | extra 11.1.2-1 | BSD-2-Clause; BSD-2-Clause-Patent; BSD-3-Clause; CC0-1.0; FSFAP; GPL-1.0-or-later; GPL-2.0-only; GPL-2.0-only WITH Linux-syscall-note; GPL-2.0-only WITH Linux-syscall-note OR BSD-2-Clause; GPL-2.0-only WITH Linux-syscall-note OR BSD-3-Clause; GPL-2.0-or-later; GPL-2.0-or-later OR BSD-3-Clause; GPL-2.0-or-later WITH Linux-syscall-note; ISC; LGPL-2.0-or-later; LGPL-2.1-only OR BSD-3-Clause; LGPL-2.1-or-later; LicenseRef-Public-Domain; MIT | M | guest |
| [qemu-chardev-spice](https://archlinux.org/packages/extra/x86_64/qemu-chardev-spice/) | extra 11.1.2-1 | BSD-2-Clause; BSD-2-Clause-Patent; BSD-3-Clause; CC0-1.0; FSFAP; GPL-1.0-or-later; GPL-2.0-only; GPL-2.0-only WITH Linux-syscall-note; GPL-2.0-only WITH Linux-syscall-note OR BSD-2-Clause; GPL-2.0-only WITH Linux-syscall-note OR BSD-3-Clause; GPL-2.0-or-later; GPL-2.0-or-later OR BSD-3-Clause; GPL-2.0-or-later WITH Linux-syscall-note; ISC; LGPL-2.0-or-later; LGPL-2.1-only OR BSD-3-Clause; LGPL-2.1-or-later; LicenseRef-Public-Domain; MIT | M | guest |
| [qemu-ui-spice-core](https://archlinux.org/packages/extra/x86_64/qemu-ui-spice-core/) | extra 11.1.2-1 | BSD-2-Clause; BSD-2-Clause-Patent; BSD-3-Clause; CC0-1.0; FSFAP; GPL-1.0-or-later; GPL-2.0-only; GPL-2.0-only WITH Linux-syscall-note; GPL-2.0-only WITH Linux-syscall-note OR BSD-2-Clause; GPL-2.0-only WITH Linux-syscall-note OR BSD-3-Clause; GPL-2.0-or-later; GPL-2.0-or-later OR BSD-3-Clause; GPL-2.0-or-later WITH Linux-syscall-note; ISC; LGPL-2.0-or-later; LGPL-2.1-only OR BSD-3-Clause; LGPL-2.1-or-later; LicenseRef-Public-Domain; MIT | M | guest |
| [apparmor](https://archlinux.org/packages/extra/x86_64/apparmor/) | extra 4.1.8-2 | GPL-2.0-only; LGPL-2.0-only; LGPL-2.1-only | O | qemu_apparmor |
| [audit](https://archlinux.org/packages/core/x86_64/audit/) | core 4.2.1-1 | GPL-2.0-or-later; LGPL-2.0-or-later | O | host_audit |
| [hypridle](https://archlinux.org/packages/extra/x86_64/hypridle/) | extra 0.1.8-2 | BSD-3-Clause | OG | host_desktop_hyprland, guest_desktop_hyprland |
| [hyprland](https://archlinux.org/packages/extra/x86_64/hyprland/) | extra 0.56.2-4 | BSD-3-Clause | OG | host_desktop_hyprland, guest_desktop_hyprland |
| [hyprlock](https://archlinux.org/packages/extra/x86_64/hyprlock/) | extra 0.9.6-3 | BSD-3-Clause | OG | host_desktop_hyprland, guest_desktop_hyprland |
| [hyprpaper](https://archlinux.org/packages/extra/x86_64/hyprpaper/) | extra 0.8.4-9 | BSD-3-Clause | O | host_desktop_hyprland |
| [hyprpolkitagent](https://archlinux.org/packages/extra/x86_64/hyprpolkitagent/) | extra 0.2.0-1 | BSD-3-Clause | OG | host_desktop_hyprland, guest_desktop_hyprland |
| [hyprshutdown](https://archlinux.org/packages/extra/x86_64/hyprshutdown/) | extra 0.1.1-8 | BSD-3-Clause | O | host_desktop_hyprland |
| [patch](https://archlinux.org/packages/core/x86_64/patch/) | core 2.8.1-1 | GPL-3.0-or-later | O | nitro_sense |
| [python-pefile](https://archlinux.org/packages/extra/any/python-pefile/) | extra 2024.8.26-2 | MIT | O | measured_boot |
| [sbsigntools](https://archlinux.org/packages/extra/x86_64/sbsigntools/) | extra 0.9.5-4 | GPL-3.0-or-later | O | measured_boot |
| [systemd-ukify](https://archlinux.org/packages/core/x86_64/systemd-ukify/) | core 262.1-1 | LGPL-2.1-or-later | O | measured_boot |
| [usbguard](https://archlinux.org/packages/extra/x86_64/usbguard/) | extra 1.1.4-11 | GPL-2.0-or-later | O | host_usbguard |
| [xdg-desktop-portal](https://archlinux.org/packages/extra/x86_64/xdg-desktop-portal/) | extra 1.22.1-2 | LGPL-2.1-or-later | OG | host_desktop_hyprland, guest_desktop_hyprland |
| [xdg-desktop-portal-hyprland](https://archlinux.org/packages/extra/x86_64/xdg-desktop-portal-hyprland/) | extra 1.4.1-2 | MIT | OG | host_desktop_hyprland, guest_desktop_hyprland |
| [awww](https://archlinux.org/packages/extra/x86_64/awww/) | extra 0.12.1-1 | GPL-3.0-only | G | guest_desktop_hyprland |
| [bash-language-server](https://archlinux.org/packages/extra/any/bash-language-server/) | extra 5.6.0-1 | MIT | G | dev_ide |
| [cliphist](https://archlinux.org/packages/extra/x86_64/cliphist/) | extra 0.7.0-2 | GPL3 | G | guest_desktop_hyprland |
| [egl-wayland](https://archlinux.org/packages/extra/x86_64/egl-wayland/) | extra 1.1.24-1 | MIT | G | guest_gpu_nvidia |
| [emacs-wayland](https://archlinux.org/packages/extra/x86_64/emacs-wayland/) | extra 31.1-2 | GPL-3.0-or-later | G | dev_ide |
| [flatpak](https://archlinux.org/packages/extra/x86_64/flatpak/) | extra 1.18.4-2 | LGPL-2.1-or-later | G | guest_desktop_hyprland (gaming-clean) |
| [gamemode](https://archlinux.org/packages/extra/x86_64/gamemode/) | extra 1.8.2-3 | BSD-3-Clause | G | guest_desktop_hyprland (gaming-clean), guest_desktop_hyprland (gaming-dirty) |
| [glib2](https://archlinux.org/packages/core/x86_64/glib2/) | core 2.90.1-1 | LGPL-2.1-or-later | G | guest_looking_glass_linux |
| [hyprlauncher](https://archlinux.org/packages/extra/x86_64/hyprlauncher/) | extra 0.1.7-1 | BSD-3-Clause | G | guest_desktop_hyprland |
| [hyprpicker](https://archlinux.org/packages/extra/x86_64/hyprpicker/) | extra 0.4.7-4 | BSD-3-Clause | G | guest_desktop_hyprland |
| [hyprsunset](https://archlinux.org/packages/extra/x86_64/hyprsunset/) | extra 0.4.0-3 | BSD-3-Clause | G | guest_desktop_hyprland |
| [imagemagick](https://archlinux.org/packages/extra/x86_64/imagemagick/) | extra 7.1.2.34-2 | ImageMagick | G | guest_desktop_hyprland |
| [jdk-openjdk](https://archlinux.org/packages/extra/x86_64/jdk-openjdk/) | extra 27.0.1.0.3.u1-1 | LicenseRef-Java | G | dev_ide |
| [kitty](https://archlinux.org/packages/extra/x86_64/kitty/) | extra 0.49.2-1 | GPL-3.0-only | G | guest_desktop_hyprland |
| [kitty-shell-integration](https://archlinux.org/packages/extra/x86_64/kitty-shell-integration/) | extra 0.49.2-1 | GPL-3.0-only | G | guest_desktop_hyprland |
| [kitty-terminfo](https://archlinux.org/packages/extra/x86_64/kitty-terminfo/) | extra 0.49.2-1 | GPL-3.0-only | G | guest_desktop_hyprland |
| [lib32-gamemode](https://archlinux.org/packages/multilib/x86_64/lib32-gamemode/) | multilib 1.8.2-1 | BSD-3-Clause | G | guest_desktop_hyprland (gaming-clean), guest_desktop_hyprland (gaming-dirty) |
| [lib32-mangohud](https://archlinux.org/packages/multilib/x86_64/lib32-mangohud/) | multilib 0.8.4-1 | MIT | G | guest_desktop_hyprland (gaming-clean), guest_desktop_hyprland (gaming-dirty) |
| [lib32-nvidia-utils](https://archlinux.org/packages/multilib/x86_64/lib32-nvidia-utils/) | multilib 615.78.08-1 | custom | G | guest_desktop_hyprland (gaming-clean), guest_desktop_hyprland (gaming-dirty) |
| [libpipewire](https://archlinux.org/packages/extra/x86_64/libpipewire/) | extra 1.6.10-1 | MIT | G | guest_looking_glass_linux |
| [linux-zen](https://archlinux.org/packages/extra/x86_64/linux-zen/) | extra 7.2.11.zen1-1 | GPL-2.0-only | G | workstation_kernel |
| [linux-zen-headers](https://archlinux.org/packages/extra/x86_64/linux-zen-headers/) | extra 7.2.11.zen1-1 | GPL-2.0-only | G | workstation_kernel, guest_looking_glass_linux |
| [lua](https://archlinux.org/packages/extra/x86_64/lua/) | extra 5.5.1-1 | MIT | G | guest_desktop_hyprland |
| [lutris](https://archlinux.org/packages/extra/any/lutris/) | extra 0.5.22-3 | GPL-3.0-only | G | guest_desktop_hyprland (gaming-dirty) |
| [mangohud](https://archlinux.org/packages/extra/x86_64/mangohud/) | extra 0.8.4-1 | MIT | G | guest_gaming_telemetry |
| [nodejs](https://archlinux.org/packages/extra/x86_64/nodejs/) | extra 26.12.1-1 | MIT | G | dev_ide |
| [npm](https://archlinux.org/packages/extra/any/npm/) | extra 12.2.1-1 | Artistic-2.0 | G | dev_ide |
| [nvidia-open-dkms](https://archlinux.org/packages/extra/x86_64/nvidia-open-dkms/) | extra 615.78.08-1 | MIT AND GPL-2.0-only | G | guest_gpu_nvidia |
| [nvidia-settings](https://archlinux.org/packages/extra/x86_64/nvidia-settings/) | extra 615.78.08-1 | GPL-2.0-only | G | guest_gpu_nvidia |
| [nvidia-utils](https://archlinux.org/packages/extra/x86_64/nvidia-utils/) | extra 615.78.08-1 | LicenseRef-NVIDIA-Driver-License-Agreement | G | guest_gpu_nvidia |
| [poppler](https://archlinux.org/packages/extra/x86_64/poppler/) | extra 26.10.0-1 | GPL-2.0-only; GPL-3.0-or-later; HPND-sell-variant; LGPL-2.0-or-later; LGPL-2.1-or-later; MIT | G | guest_safe_documents |
| [python](https://archlinux.org/packages/core/x86_64/python/) | core 3.14.8-1 | PSF-2.0 | G | dev_ide |
| [python-pygments](https://archlinux.org/packages/extra/any/python-pygments/) | extra 2.21.0-1 | BSD-2-Clause | G | guest_desktop_hyprland |
| [rofi-calc](https://archlinux.org/packages/extra/x86_64/rofi-calc/) | extra 2.5.1-1 | MIT | G | guest_desktop_hyprland |
| [shellcheck](https://archlinux.org/packages/extra/x86_64/shellcheck/) | extra 0.11.0-163 | GPL | G | dev_ide |
| [steam](https://archlinux.org/packages/multilib/x86_64/steam/) | multilib 1.0.0.87-3 | LicenseRef-steam-subscriber-agreement | G | guest_desktop_hyprland (gaming-clean) |
| [thunar](https://archlinux.org/packages/extra/x86_64/thunar/) | extra 4.20.10-1 | GPL-2.0-or-later; LGPL-2.1-only | G | guest_desktop_hyprland |
| [thunar-archive-plugin](https://archlinux.org/packages/extra/x86_64/thunar-archive-plugin/) | extra 0.6.0-1 | GPL-2.0-only | G | guest_desktop_hyprland |
| [ttf-ibm-plex](https://archlinux.org/packages/extra/any/ttf-ibm-plex/) | extra 6.4.0-2 | custom:OFL | G | guest_desktop_hyprland |
| [tumbler](https://archlinux.org/packages/extra/x86_64/tumbler/) | extra 4.20.2-2 | GPL-2.0-or-later | G | guest_desktop_hyprland |
| [typescript-language-server](https://archlinux.org/packages/extra/any/typescript-language-server/) | extra 6.0.0-1 | Apache-2.0; MIT | G | dev_ide |
| [vkmark](https://archlinux.org/packages/extra/x86_64/vkmark/) | extra 2025.01-2 | LGPL-2.1-only | G | guest_gaming_telemetry |
| [vulkan-icd-loader](https://archlinux.org/packages/extra/x86_64/vulkan-icd-loader/) | extra 1.4.363.0-1 | Apache-2.0 | G | guest_gpu_nvidia |
| [wine](https://archlinux.org/packages/extra/x86_64/wine/) | extra 11.20-1 | LGPL-2.1-or-later | G | guest_desktop_hyprland (gaming-dirty) |
| [winetricks](https://archlinux.org/packages/extra/any/winetricks/) | extra 20260125-2 | LGPL-2.1-or-later | G | guest_desktop_hyprland (gaming-dirty) |

`iptables-nft` in `kvm_host_packages` has no package record of that name:
core `iptables` 1.8.13-1 provides and replaces it. This is a package-name
finding, not a licence one ([section 11](#11-findings-outside-licensing)).

## 3. Pinned upstream sources built on a target

### Looking Glass

`looking_glass` (host default) and `guest_looking_glass_linux` (VFIO guests)
clone [gnif/LookingGlass](https://github.com/gnif/LookingGlass) recursively at
`0140a3f6fb616c5636d6c430eb71b8a7d5338e39` (build identity
`B7-263-g0140a3f6fb`, committed 2026-07-16) and build on the target:

- the **client** (`client/`, CMake with Wayland and libdecor) on the host,
  after applying `client-captured-button-press.patch`;
- the **kvmfr** kernel module (`module/`, `dkms install`) on the host;
  `kvmfr.c` declares GPL-2.0-or-later in its header and
  `MODULE_LICENSE("GPL v2")`, version 0.0.12;
- the **Linux sender** (`host/`) in VFIO guests, after applying the two
  PipeWire patches.

The repository's root `LICENSE` at the pin is the GPL-2.0 text (sha256
`8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643`); the source
headers read (the three patched files and `kvmfr.c`) state GPL-2.0-or-later.
Outside the submodules, the tree at the pin (564 entries) has no other file
named `LICENSE`, `COPYING` or `NOTICE`. The recursive clone also fetches
these submodules at the revisions the pin records:

| Submodule | Pinned revision | Licence file at that revision |
| --- | --- | --- |
| `repos/LGMP` ([gnif/LGMP](https://github.com/gnif/LGMP)) | `149c731050d28c93532ee5ab4c84dfe6c2342f49` | GPL-2.0 text (same digest as above) |
| `repos/LGMP/relacy` ([dvyukov/relacy](https://github.com/dvyukov/relacy)) | `acc09bbe65a1837a08912774c7fed178547514e6` | three-clause BSD-style, "Copyright (c) 2008-2013, Dmitry S. Vyukov" |
| `repos/PureSpice` ([gnif/PureSpice](https://github.com/gnif/PureSpice)) | `8177f993b04fd3193d3437c53fcc2fcd97bb938f` | GPL-2.0 text (same digest) |
| `repos/PureSpice/test/ADL` ([gnif/ADL](https://github.com/gnif/ADL)) | `155324534e334383c76e7ba1f4736e0c4209b83b` | MIT, "Copyright (c) 2020 Geoffrey McRae" |
| `repos/cimgui` ([cimgui/cimgui](https://github.com/cimgui/cimgui)) | `d6b4ecda718352bb4adcd30ec25784fd16538b73` | MIT, "Copyright (c) 2015 Stephan Dilly" |
| `repos/cimgui/imgui` ([ocornut/imgui](https://github.com/ocornut/imgui)) | `dbb5eeaadffb6a3ba6a60de1290312e5802dba5a` | MIT, "Copyright (c) 2014-2025 Omar Cornut" |
| `repos/nanosvg` ([memononen/nanosvg](https://github.com/memononen/nanosvg)) | `cb0ae54e6b147ccdf85401ef3ef20f2c761252c0` | zlib, "Copyright (c) 2013-14 Mikko Mononen" |
| `repos/wayland-protocols` ([quantum5/wayland-protocols](https://github.com/quantum5/wayland-protocols)) | `02e63e74a807afed95bc25a386173110afef24e3` | MIT text with the Wayland protocol copyright holders |

Revisions were read from the GitHub contents API and the licence files from
each repository at those revisions on 2026-10-27. Which of these the client
or the sender actually compiles in was not established from the build files;
an image that ships either binary has to establish it (S7). Per-file headers
other than the four named above were not read.

The build happens on the target from upstream source; nothing built is
redistributed by this repository. Shipping a built client, sender or kvmfr
module would mean distributing GPL-2.0-or-later binaries with their
corresponding source, including the patches, and the notices of the
submodules that are compiled in.

### Linuwu-Sense (optional)

`nitro_sense` builds [0x7375646F/Linuwu-Sense](https://github.com/0x7375646F/Linuwu-Sense)
at `73a25ec243a44ba2b1703e8d0a76fa2735062506` (committed 2026-03-13) with
`an515-55-four-zone.patch`, through DKMS, only when
`nitro_sense_out_of_tree_enabled` is set (default `false`). The project
`LICENSE` is the GPL-3.0 text; `src/linuwu_sense.c` declares
`SPDX-License-Identifier: GPL-2.0-or-later`, keeps the acer-wmi copyright
lines and `MODULE_LICENSE("GPL")`.

### Eclipse JDT Language Server

`dev_ide` downloads `jdt-language-server-1.60.0-202606262232.tar.gz` from
`https://download.eclipse.org/jdtls/milestones/1.60.0/` into dev guests and
verifies it against the upstream `.sha256` file before extraction. The
project's `LICENSE` at tag `v1.60.0` of
[eclipse-jdtls/eclipse.jdt.ls](https://github.com/eclipse-jdtls/eclipse.jdt.ls)
is the Eclipse Public License 2.0. The archive's bundled dependencies were
not inventoried (S7).

## 4. NVIDIA components

`guest_gpu_nvidia` installs the following inside VFIO workstation guests
only; the host never installs an NVIDIA driver. The stack is **not** open
source as a whole and is **not** freely redistributable as a whole:

| Package (615.78.08-1) | What it carries | Terms recorded |
| --- | --- | --- |
| `nvidia-open-dkms` | source of NVIDIA's open GPU kernel modules, built by DKMS in the guest | `MIT AND GPL-2.0-only`; the package installs upstream `COPYING` as its licence ([NVIDIA/open-gpu-kernel-modules](https://github.com/NVIDIA/open-gpu-kernel-modules) tag `615.78.08`: MIT except where files say otherwise) |
| `nvidia-utils` | proprietary userspace driver libraries and tools, **and** GPU System Processor firmware (`usr/lib/firmware/nvidia/615.78.08/gsp_ga10x.bin`, `gsp_tu10x.bin`, `ucodes_ga10x.bin`, `ucodes_tu10x.bin`) | `LicenseRef-NVIDIA-Driver-License-Agreement`; the text is the `LICENSE` of NVIDIA's `.run` installer, installed as `/usr/share/licenses/nvidia-utils/LICENSE` |
| `lib32-nvidia-utils` (gaming profiles) | 32-bit proprietary userspace | `custom` |
| `nvidia-settings` | configuration tool | `GPL-2.0-only` |
| `egl-wayland` | EGL external platform library | `MIT` |

The Arch `PKGBUILD` at tag `615.78.08-1`
(`https://gitlab.archlinux.org/archlinux/packaging/packages/nvidia-utils`)
builds the userspace and firmware from
`https://download.nvidia.com/XFree86/Linux-x86_64/615.78.08/NVIDIA-Linux-x86_64-615.78.08.run`
and the open modules from NVIDIA's open kernel module source tarball. The
NVIDIA driver licence text itself was not read for this report: its
conditions for copying the userspace and firmware into an image are unknown
here (S5). The open kernel modules' source terms do not extend to the
userspace or the firmware.

## 5. Fonts, icons and themes

No font, icon or third-party theme file is tracked. Packages:

| Package | Version | Arch record licence | Licence file in the package | Installed by |
| --- | --- | --- | --- | --- |
| `ttf-jetbrains-mono-nerd` | 3.5.1-2 | OFL-1.1-no-RFN | `/usr/share/licenses/ttf-jetbrains-mono-nerd/OFL.txt` | host default, guests |
| `noto-fonts` | 2026.10.01-1 | OFL-1.1-no-RFN | `/usr/share/licenses/noto-fonts/LICENSE` | host default, guests |
| `ttf-ibm-plex` | 6.4.0-2 | `custom:OFL` | `/usr/share/licenses/ttf-ibm-plex/license.txt` | guests |
| `ttf-dejavu` | 2.37+18+g9b5d1b2f-8 | `custom` | `/usr/share/licenses/ttf-dejavu/LICENSE` | host default (`looking_glass`) |
| `papirus-icon-theme` | 20260801-1 | GPL-3.0 (no "only" or "or later" in the record) | none under `/usr/share/licenses/` | host default, guests |

The Nerd Font package merges icon glyphs from several projects; the record
names one licence for the package, and the terms of each merged glyph set
were not read. The GTK, Rofi, Waybar, Quickshell and terminal styling are
the repository's own files (section 1); the Catppuccin values they use are
noted in section 9. The Emacs `nerd-icons` and `doom-modeline` packages come
from MELPA (section 6).

## 6. Other remote sources

| Source | Where | Pin | Licence evidence (2026-10-27) | Class |
| --- | --- | --- | --- | --- |
| Ansible collections `community.general`, `community.libvirt` ([`collections/requirements.yml`](../collections/requirements.yml)) | controller, from Ansible Galaxy | **none**: the newest release is installed (13.5.0 and 2.4.0 on Galaxy) | `COPYING` is GPL-3.0 in both at those tags; `community.general` also ships `LICENSES/BSD-2-Clause.txt` and `LICENSES/MIT.txt` | controller tool, not installed on a target |
| npm `vscode-langservers-extracted`, `@ansible/ansible-language-server` | dev guests, global | **none** (4.10.0 and 26.6.0 latest) | registry `license`: MIT for both; their dependency trees not read | G |
| Emacs packages `nerd-icons`, `doom-modeline`, `vertico`, `orderless`, `marginalia`, `consult`, `corfu`, `yaml-mode`, `magit`, `eat` | dev guests, `package-install` | **none** | the role adds MELPA to Emacs's default GNU and NonGNU ELPA archives; `eat` is not on MELPA and is published on NonGNU ELPA (0.9.4); the others are on MELPA with date versions, and five are also on GNU ELPA; which archive serves each was not observed; per-package licences and dependencies not read | G |
| Flathub `com.heroicgameslauncher.hgl` | `gaming-clean` guests | **none** (v2.22.4 listed) | Flathub `project_license`: GPL-3.0; its runtime not read | G |
| Jellyfin APT repository through `extrepo` (`https://repo.jellyfin.org/debian`) | `svc-jellyfin` service VM (Debian 13) | **none** | upstream `LICENSE` of [jellyfin/jellyfin](https://github.com/jellyfin/jellyfin) is GPL-2.0; the `jellyfin` package's dependencies (server, web client, its FFmpeg build) not read; `extrepo` 0.14 and `ca-certificates` 20250419 are Debian trixie packages whose `copyright` files were not read | service VM |
| Official cloud images (`images/arch.yml`, `images/debian.yml`, `images/fedora.yml`) | host image store, `image_factory` | version, URL and sha256 pinned in each manifest | each is an operating-system image aggregating many packages under their own terms; contents not inventoried; the manifests' `licensing.redistributable: true` is the manifest's own statement, not a result of this audit | M |
| Private guest wallpaper bundle (`guest_visual_assets`) | guests, from an operator-supplied URL | sha256 required; the default URL is empty | operator-owned media; not in the repository and not audited | operator input |
| Local and Windows images (`images/arch-*`, `images/win11*`, `images/parrot.yml`, `images/debian-server.yml`) | host image store | local imports | Windows images are `private: true` and `licensing.redistributable: false`; their contents (Windows, NVIDIA Windows driver, the Looking Glass Windows host, a virtual display driver) are operator-installed and outside this audit | operator input |

## 7. Build and verification tools (not shipped)

The CI workflow (`.github/workflows/ci.yml`) runs on GitHub-hosted Ubuntu
runners: `actions/checkout@v4`, `actions/upload-artifact@v4`, Ubuntu packages
(`shellcheck`, `bats`, `nftables`, `lua5.4`, `poppler-utils`, `pkg-config`,
`libpipewire-0.3-dev`, `libglib2.0-dev`, `pciutils`, `qmlscene-qt6` and four
`qml6-module-*` packages), and `pip install --user ansible ansible-lint ruff`
and `pip install pyyaml`, all unpinned. `verify.sh` uses the same tools
locally. They test the repository and are not part of anything it installs
or distributes; the Qt version matters only for the byte-stable wallpaper
renders in section 1.

## 8. Distribution modes

| Component | In this Git repository (source) | Installed later by a playbook | Bundled into a live image or ISO |
| --- | --- | --- | --- |
| First-party files (`declared`) | published under the root MIT declaration | copied to the host and guests | not admitted: awaits the maintainer's confirmation (S4) and an audited payload |
| Generated files (`documented`) | published; reproducible from tracked generators | copied to the host | not admitted: same as above |
| The four patches | published; GPL-2.0-or-later, not MIT (S3) | applied to upstream source on the target | only with the full corresponding source, the upstream notices and the GPL text |
| The 105 images without provenance | already public; provenance/permission pending (S1, S2) | 94 installed by `host_desktop_sway`; trust-v2 images also copied into guests | **blocked** until their provenance and permission are recorded |
| Arch packages | not in the repository | fetched from the mirrors on each apply | **blocked** pending the resolved closure, its notices and corresponding source (S7) |
| Looking Glass, Linuwu-Sense, JDT LS | not in the repository; pinned URL and revision | cloned or downloaded and built on the target | **blocked** pending source delivery and the compiled-in submodules (S7) |
| NVIDIA userspace and firmware | not in the repository | inside VFIO guests only | **blocked**: driver licence terms not read (S5) |
| Steam, JDK, custom and unversioned licences | not in the repository | inside guests | **blocked** pending the terms (S6) |
| Collections, npm, Emacs, Flathub, Jellyfin APT | not in the repository; unpinned | controller, guests or the service VM | not admitted: no pinned version to audit (S8) |
| Cloud and private images | not in the repository | downloaded or imported into the host store | private images excluded; cloud images not admitted (S9) |

Being tracked in a public repository does not admit anything into an image:
unknown or incompatible material stays out until its entry here is resolved.
Release qualification and the ISO gate in the [roadmap](roadmap.md) stay open;
completing this inventory is not ISO clearance.

## 9. Third-party notices

The following attributions are supported by the evidence above. The
patches keep their upstream notices in the repository unchanged.

**Looking Glass** (the three Looking Glass patches modify its files):

```text
Looking Glass
Copyright © 2017-2026 The Looking Glass Authors
https://looking-glass.io

This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation; either version 2 of the License, or (at your option)
any later version.
```

**Linuwu-Sense / acer-wmi** (the Nitro patch modifies `src/linuwu_sense.c`,
whose header reads):

```text
SPDX-License-Identifier: GPL-2.0-or-later
Acer WMI Laptop Extras
Copyright (C) 2007-2009 Carlos Corbacho
Based on acer_acpi:
  Copyright (C) 2005-2007 E.M. Smith
  Copyright (C) 2007-2008 Carlos Corbacho
```

**Catppuccin palette** (colour values used in `ui.py`, `mako.conf` and
`starship.toml`):

```text
MIT License

Copyright (c) 2021 Catppuccin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

No notice is given for the 105 images: no attribution for them is supported
by evidence.

## 10. Unresolved

Each item is an operator action, not a conclusion of this report. Nothing
here declares an infringement or grants a permission.

| Id | What | Missing evidence | Blocks |
| --- | --- | --- | --- |
| S1 | the 22 images of `themes/assets/hyperlab-symbols-v1/` and `themes/assets/hyperlab-trust-v2/` | source, rights holder, terms and permission for each file | these files in any image, their attribution, and closing the licence review |
| S2 | the 83 legacy images: `roles/host_desktop_sway/files/wallpapers/{blue,green,red,violet}/01..20.png`, `wallpaper-desktop.png`, `wallpaper-lockscreen.png`, `wallpaper.png` | same as S1 | the same, for the legacy pools the host default still installs |
| S3 | the four GPL-2.0-or-later patches in a repository whose `README.md` and `LICENSE` name MIT only; the narrower licence statement in `nitro-sense.md` | a decision on where the exception is stated | an accurate licence statement for the repository |
| S4 | the 1135 `declared` rows, including the seven SVG files and the "written from scratch" statement | the maintainer's confirmation of authorship, or the source and terms of any exception | final attributions and the admission of first-party files into an image |
| S5 | NVIDIA userspace and GSP firmware (`nvidia-utils`, `lib32-nvidia-utils`) | the driver licence's terms for copying into an image | any NVIDIA userspace or firmware in an image |
| S6 | `steam` (subscriber agreement), `jdk-openjdk` (`LicenseRef-Java`), `custom` records (`ttf-dejavu`, `ttf-ibm-plex`, `lib32-nvidia-utils`, `libglvnd`, `libva-utils`), `imagemagick` (`ImageMagick`), unversioned records (`shellcheck`, `virt-viewer` "GPL", `make`, `cliphist` "GPL3", `papirus-icon-theme`, `libsamplerate` "BSD") | the text of each licence for the exact version | those packages in an image |
| S7 | dependency closures: Arch packages, the Looking Glass build (compiled-in submodules), JDT LS bundles, collection contents, npm and Emacs dependency trees, the Flathub runtime, the Jellyfin APT closure | a resolved closure with versions, licence texts, notices and corresponding source | any image that carries them |
| S8 | unpinned sources: Galaxy collections, npm, Emacs archives, Flathub, Jellyfin APT, and Arch itself | a pinned version to audit | admitting the audited version as the shipped one |
| S9 | cloud images and private images | the content inventory of the cloud images; private images are not redistributable by their manifests | any redistribution of an image |

## 11. Findings outside licensing

- `kvm_host_packages` names `iptables-nft`, for which the Arch repositories
  have no package of that name on 2026-10-27; core `iptables` 1.8.13-1
  provides and replaces it. Whether `community.general.pacman` reports the
  provided name as installed was not checked here.
- [`nitro-sense.md`](nitro-sense.md) states the upstream licence as GPL-3.0
  and that no upstream source is vendored; see
  [section 1](#patches-of-upstream-source).
