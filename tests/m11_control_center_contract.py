#!/usr/bin/env python3
"""Focused M11 v7 HyperLab Shell visual-lock contract."""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    manager_path = "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
    manager = text(manager_path)
    compile(manager, manager_path, "exec")
    ast.parse(manager)
    manager_session = text(
        "roles/host_desktop_sway/files/privatestack-hyperlab-session.sh"
    )

    for boundary in (
        'CDLL("libgtk4-layer-shell.so")',
        'gi.require_version("Gdk", "4.0")',
        'gi.require_version("Gtk", "4.0")',
        'gi.require_version("Gtk4LayerShell", "1.0")',
        "LayerShell.init_for_window(self)",
        "LayerShell.Layer.OVERLAY",
        "LayerShell.KeyboardMode.ON_DEMAND",
    ):
        require(boundary in manager, "Layer Shell boundary missing: %s" % boundary)
    require("class HyperlabWindow(Gtk.Window)" in manager,
            "Layer Shell window class missing")
    require("Gtk.ApplicationWindow" not in manager,
            "normal tiled ApplicationWindow returned")
    require('surface_mode in {"drawer", "overlay"}' in manager,
            "drawer/overlay surface contract missing")
    require("panel.set_size_request(500, 560)" in manager,
            "compact fixed-size drawer missing")
    require("panel.set_size_request(1180, 760)" in manager,
            "target-size central manager missing")
    require("LayerShell.Edge.TOP" in manager and
            "LayerShell.Edge.RIGHT" in manager and
            "LayerShell.Edge.BOTTOM" in manager and
            "LayerShell.Edge.LEFT" in manager,
            "single cockpit surface does not cover the usable output")
    require("LayerShell.set_margin(self, LayerShell.Edge.TOP, 0)" in manager and
            "panel.set_margin_top(0)" in manager and
            "panel.set_margin_start(0)" in manager,
            "drawer no longer lands flush-left below Waybar")
    require('gapplication action "${app_id}" quit' in manager_session and
            "flock -n 9" in manager_session and
            'exec "${manager}" --warm' in manager_session,
            "reload-safe resident manager replacement is missing")
    require('kill -TERM "${manager_pids[@]}"' in manager_session and
            "kill -KILL" not in manager_session,
            "manager replacement is not bounded and graceful")
    require('.config/gtk-4.0/hyperlab-palette.css' in manager and
            "self._style_provider.load_from_data" in manager and
            'palette.read_text(encoding="utf-8")' in manager,
            "manager is disconnected from the runtime-selected palette")
    require('background: @hl_base' in manager,
            "opaque non-blurred manager surface missing")
    require("class HyperlabBackdropWindow(Gtk.Window)" not in manager and
            "root = Gtk.Overlay()" in manager and
            "hyperlab-backdrop-catcher" in manager and
            "root.add_overlay(panel)" in manager,
            "single-surface click-outside layout missing")
    require("ThreadPoolExecutor" in manager and "as_completed" in manager and
            "timeout=5.0" in manager,
            "bounded parallel status loading missing")
    require("def keep_warm" in manager and "self.hold()" in manager and
            'value == "--warm"' in manager and
            'self._ensure_window("drawer", "vms")' in manager and
            "self.windows: dict[str, HyperlabWindow]" in manager,
            "prebuilt resident drawer missing")
    require('header.append(text_label("Machines" if compact else "HyperLab", "mock-title"' in manager and
            'self.header_status = text_label("Loading…", "mock-badge"' in manager,
            "definitive minimal titlebar is missing")
    require("Gtk.EventControllerKey()" in manager and
            "Gtk.PropagationPhase.CAPTURE" in manager and
            "keyval == Gdk.KEY_Escape" in manager,
            "single-Escape close capture missing")
    require("LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)" in manager and
            "LayerShell.KeyboardMode.NONE" not in manager,
            "HyperLab surface no longer preserves normal desktop keyboard focus")
    require("def close_visible_surfaces" in manager and
            "catcher = Gtk.Button()" in manager and
            'lambda *_args: self.close_surface()' in manager,
            "single-surface click-outside close path is missing")
    require("self.set_visible(False)" in manager and
            "def close_surface" in manager,
            "resident hide/reopen close path missing")
    require('for other_surface, other in self.windows.items()' in manager and
            'window.present()' in manager and
            'GLib.timeout_add(120, self._refresh_visible_windows)' in manager,
            "resident drawer/overlay switching is not immediate")
    require('surface = "drawer"' in manager,
            "the no-argument HyperLab route is not the compact drawer")
    require("def _build_quick_actions" not in manager,
            "obsolete oversized drawer quick-actions surface returned")
    require('rail.set_size_request(170, -1)' in manager and
            'self.stack.add_css_class("mock-main")' in manager and
            'self.inspect_holder.set_size_request(300, -1)' in manager,
            "definitive 170/main/300 Control Center geometry is missing")
    require("panel.set_margin_top(40)" in manager,
            "Control Center is not pinned 40 px below the 37 px Waybar")
    for section, label in (("vms", "Machines"), ("create", "Create"),
                           ("policies", "Networks"), ("gpu", "GPU"),
                           ("nitro", "Nitro")):
        require(f'(\"{section}\", \"{label}\")' in manager,
                "definitive rail section missing: %s" % label)
    require('("overview", "Overview")' not in manager.split("navigation = [", 1)[1].split("]", 1)[0],
            "legacy nine-section rail returned")
    require('content.append(self._build_vm_showcase(columns=2, compact=True))' in manager and
            'showcase = self._build_vm_showcase(columns=4)' in manager,
            "drawer/full machine showcases do not match the 2/4-column mockup")
    require('canvas = Gtk.Fixed()' in manager and
            'canvas.add_css_class("network-canvas")' in manager and
            'content.append(dock)' in manager and
            'self.inspect_holder.set_visible(section != "policies")' in manager,
            "Networks does not use the agreed full-width graph plus docked inspector")
    require('rung.add_css_class("gpu-rung")' in manager and
            'ladder = ((0, ("clean", "dev")), (1, ("services",)), (2, ("dirty",)), (3, ("lab",)))' in manager,
            "definitive four-rung GPU ladder is missing")
    for capability in (
        "Looking Glass", "SPICE recovery", "linux-experimental",
        "Preview / dry-run", "Write spec and create", "disposable",
        "Nitro", "Apply fan values", "Apply battery limiter",
        "Apply four-zone RGB",
    ):
        require(capability in manager, "HyperLab capability missing: %s" % capability)
    require("shell=True" not in manager and "os.system" not in manager and "eval(" not in manager,
            "manager introduced a shell execution boundary")
    require("chromium" not in manager.lower() and "webkit" not in manager.lower(),
            "browser dependency leaked into shell")
    require("arch-dev-01" not in manager,
            "synthetic mockup VM leaked into runtime")
    for stale_phrase in ("VM collegate", "Domini", "Prepara / importa", "Mostra JSON", "Continua"):
        require(stale_phrase not in manager,
                "non-English runtime UI text remains: %s" % stale_phrase)

    defaults = text("roles/host_desktop_sway/defaults/main.yml")
    for package in (
        "gtk4", "gtk4-layer-shell", "python-gobject", "virt-viewer",
        "nemo", "gvfs", "gvfs-mtp", "gvfs-smb", "gvfs-nfs",
        "udisks2", "file-roller", "ffmpeg", "ffmpegthumbnailer",
        "mpv", "celluloid", "pavucontrol",
        "pipewire", "pipewire-audio", "pipewire-alsa",
        "pipewire-pulse", "wireplumber", "gst-plugin-pipewire",
        "gst-plugins-base", "gst-plugins-good", "gst-plugins-bad",
        "gst-plugins-ugly", "gst-libav",
        "mesa", "vulkan-intel", "vulkan-tools",
        "intel-media-driver", "libva-utils",
        "jq", "wayland-utils",
    ):
        require("  - %s\n" % package in defaults,
                "desktop package missing: %s" % package)
    require(
        "host_desktop_sway_removed_packages:\n"
        "  - yazi\n"
        "  - cava\n"
        "  - superfile\n" in defaults,
        "retired desktop package removal policy missing",
    )

    tasks = text("roles/host_desktop_sway/tasks/main.yml")
    palette_tasks = text("roles/host_desktop_sway/tasks/palette.yml")
    require("/usr/local/bin/privatestack-cava" in tasks and
            "/usr/local/bin/privatestack-fullscreen" in tasks and
            "/usr/local/bin/privatestack-superfile" in tasks and
            '.config/superfile' in tasks and
            'state: absent' in tasks,
            "retired desktop helpers are not removed from existing hosts")
    for deployed in (
        "hyperlab-gtk.css",
        "hyperlab-wallpaper.svg", "hyperlab-control-center.svg",
        "privatestack-hyperlab-domains.py", "privatestack-hyperlab-session.sh",
        "privatestack-waybar.sh",
        "privatestack-theme.sh",
        "privatestack-keyboard.sh", "privatestack-controls.sh",
        "privatestack-swaylock.sh", "privatestack-swaybar-status.py",
    ):
        require(deployed in tasks, "visual-lock asset not deployed: %s" % deployed)
    require("superfile-config.toml" not in tasks and
            "privatestack-superfile.sh" not in tasks,
            "retired Superfile assets still have active desktop ownership")
    require("superfile/theme/hyperlab.toml" not in palette_tasks and
            "hyperlab-palette-superfile.toml" not in palette_tasks,
            "retired Superfile palette still has active ownership")
    require("Install every runtime palette fragment" in palette_tasks and
            "Install the selected palette into user-owned active files" in palette_tasks and
            "hyperlab-palette-gtk.css" in palette_tasks and
            "hyperlab-palette-swaylock.conf" in palette_tasks,
            "runtime palettes are not installed into read-only pools and active user files")
    require("/usr/share/icons/hyperlab/domains" in tasks and
            "Deploy the Qubes-style domain cube icons" in tasks,
            "domain cube deployment is missing")
    require("/usr/share/backgrounds/privatestack/hyperlab.svg" in tasks,
            "editable vector wallpaper is not installed")
    require("gtk-3.0/gtk.css" in tasks and "gtk-4.0/gtk.css" in tasks,
            "global HyperLab GTK theme is not deployed to GTK3 and GTK4")

    gtk_theme = text("roles/host_desktop_sway/files/hyperlab-gtk.css")
    # The GTK sheet imports the generated shared palette instead of carrying
    # a second private source of truth.
    for marker in ('@import url("hyperlab-palette.css")',
                   "background-color: alpha(@hl_base, 0.48)",
                   "background-color: alpha(@hl_mantle, 0.54)"):
        require(marker in gtk_theme, "global GTK visual token missing: %s" % marker)

    sway = text("roles/host_desktop_sway/files/sway.config")
    require("output * bg /usr/share/backgrounds/privatestack/public/green/01.png fill" in sway,
            "Green wallpaper pool fallback path missing")
    require("rofi -show drun -theme ~/.config/rofi/rofi-launcher.rasi" in sway,
            "Mod+d does not select the HyperLab Rofi theme explicitly")
    require("set $filemanager nemo" in sway and
            "bindsym $mod+Shift+f exec $filemanager" in sway,
            "Mod+Shift+f does not launch the managed Nemo file manager")
    require("superfile" not in sway,
            "retired Superfile policy remains in the live Sway configuration")
    require("bindsym $mod+o exec /usr/local/bin/privatestack-opacity-toggle" in sway,
            "Mod+o does not reach the opacity toggle")
    for direction in ("Left", "Down", "Up", "Right"):
        require("bindsym $mod+Shift+%s move %s" % (direction, direction.lower()) in sway,
                "physical arrow move binding missing: %s" % direction)
    for opacity in (
        'for_window [app_id="^foot$"] opacity 0.82',
        'for_window [app_id="^floatterm$"] opacity 0.80',
        'for_window [app_id="^hyperlab-operation$"] opacity 0.84',
    ):
        require(opacity in sway, "transparent Sway rule missing: %s" % opacity)
    require("bindsym $mod+f fullscreen toggle" in sway,
            "stable native fullscreen binding is missing")
    require("status_command /usr/local/bin/privatestack-swaybar-status" in sway and
            "id bar-0" in sway and "mode invisible" in sway,
            "native Swaybar crash fallback is missing")
    require("bindsym $mod+Shift+b exec /usr/local/bin/privatestack-waybar toggle" in sway,
            "supervised Waybar visibility binding is missing")
    require("bindsym $mod+Shift+t exec /usr/local/bin/privatestack-theme cycle" in sway,
            "four-theme cycle shortcut is missing")
    require("bindsym $mod+Shift+w exec /usr/local/bin/privatestack-theme mode-toggle" in sway,
            "public/personal wallpaper shortcut is missing")
    require("exec_always /usr/local/bin/privatestack-waybar" in sway and
            "exec_always /usr/local/bin/privatestack-hyperlab-session" in sway,
            "supervised bar or warm control plane is not active")
    require("exec_always /usr/local/bin/privatestack-theme session-start" in sway and
            "exec_always /usr/local/bin/privatestack-theme daemon" in sway,
            "theme state or wallpaper rotation is not started by Sway")

    waybar_launcher = text("roles/host_desktop_sway/files/privatestack-waybar.sh")
    require("waybar -l info -c" in waybar_launcher and
            "waybar.log" in waybar_launcher and
            "flock -n 9" in waybar_launcher and
            "9>&-" in waybar_launcher and
            "failures >= 3" in waybar_launcher and
            "native_bar" in waybar_launcher,
            "single-instance supervised Waybar fallback contract missing")
    swaybar_status = text("roles/host_desktop_sway/files/privatestack-swaybar-status.py")
    require('"click_events": True' in swaybar_status and
            'block("theme", theme.upper()' in swaybar_status and
            '["/usr/local/bin/privatestack-theme", "cycle"]' in swaybar_status,
            "native Swaybar status lacks the clickable theme control")
    theme_helper = text("roles/host_desktop_sway/files/privatestack-theme.sh")
    require("public_wallpaper_count=20" in theme_helper and
            "personal_wallpaper_count" in theme_helper and
            "active_wallpaper_count" in theme_helper and
            "readonly themes=(green violet blue red)" in theme_helper and
            "wallpaper_mode_file" in theme_helper and
            "lock_index=$(( (desktop_index + 3) % count ))" in theme_helper and
            "HYPERLAB_WALLPAPER_INTERVAL" in theme_helper,
            "theme helper lacks four themes, source mode, rotation or lock separation")
    swaylock_helper = text("roles/host_desktop_sway/files/privatestack-swaylock.sh")
    require("privatestack-theme lock-image" in swaylock_helper,
            "swaylock does not request a distinct theme-aware image")

    waybar = text("roles/host_desktop_sway/files/waybar.jsonc")
    require('"height": 37' in waybar, "Nitro-compatible Waybar height missing")
    require('"layer": "top"' in waybar and '"mode": "dock"' in waybar and
            '"exclusive": true' in waybar and '"ipc": false' in waybar,
            "Waybar is not the exclusive primary status surface")
    require(
        '"modules-left": ["sway/workspaces", "custom/brand", "group/hyperlab", "sway/mode"]'
        in waybar,
        "Waybar no longer mirrors the definitive workspace/HyperLab left zone",
    )
    require('"format": "  HyperLab"' in waybar,
            "Waybar cube brand label missing")
    require('"format": "TRUST {}"' in waybar and
            '"children-class": "trust-detail"' in waybar and
            '"reveal-delay": 40' in waybar,
            "trust hover drawer is not configured")
    require('"modules-center": ["clock"]' in waybar,
            "clock is not centered")
    require('"modules-right": ["group/telemetry", "group/session"]' in waybar,
            "right-side Waybar pods are wrong")
    require('"modules": ["temperature", "network", "pulseaudio", "battery"]' in waybar,
            "telemetry pod is incomplete")
    require('"modules": ["custom/keyboard-layout", "custom/wallpaper-mode", "custom/controls"]' in waybar,
            "session-control pod is incomplete")
    for route in (
        "privatestack-hyperlab-domains --surface drawer --section vms",
        "privatestack-hyperlab-domains --surface drawer --section diagnostics",
        "privatestack-hyperlab-domains --surface overlay --section vms",
        "privatestack-hyperlab-domains --surface overlay --section diagnostics",
    ):
        require(route in waybar, "HyperLab Waybar route missing: %s" % route)
    require(
        '"on-click-middle": "/usr/local/bin/privatestack-hyperlab-domains --surface overlay --section vms"'
        in waybar,
        "HyperLab middle click does not open the full Control Center",
    )
    require(
        '"on-click-middle": "/usr/local/bin/privatestack-hyperlab-domains --surface overlay --section diagnostics"'
        in waybar,
        "TRUST middle click does not open full System diagnostics",
    )
    for stale_module in (
        "custom/cava", "custom/logo", "idle_inhibitor", "cpu", "memory",
        "backlight", "tray",
    ):
        require(('"%s"' % stale_module) not in waybar,
                "unused Waybar module returned: %s" % stale_module)
    waybar_css = text("roles/host_desktop_sway/files/waybar.css")
    for stale_selector in (
        "#custom-cava", "#custom-logo", "#idle_inhibitor", "#cpu",
        "#memory", "#backlight", "#tray",
    ):
        require(stale_selector not in waybar_css,
                "retired Waybar CSS selector returned: %s" % stale_selector)
    require('window.set_visible(True)' in manager and
            'self._open_full_manager("create") if compact else self.select_section("create")' in manager,
            "resident drawer mapping or New machine escape hatch missing")

    waybar_css = text("roles/host_desktop_sway/files/waybar.css")
    for marker in (
        "min-height: 37px",
        "#workspaces",
        "#custom-brand",
        "#hyperlab",
        "#clock",
        "#telemetry",
        "#session",
        'font-family: "Inter", "Adwaita Sans", "Cantarell", sans-serif',
    ):
        require(marker in waybar_css, "Waybar definitive-mockup marker missing: %s" % marker)
    require("window#waybar.hidden { opacity: 0; }" not in waybar_css,
            "Waybar can still become fully transparent while running")
    require('@import url("palette.css")' in waybar_css,
            "Waybar is disconnected from the runtime-selected user palette")
    require("--reload-theme" in manager and "def reload_theme" in manager,
            "resident manager cannot reload Green/Violet palettes")
    for token in ("@hl_dom_clean", "@hl_dom_dev", "@hl_dom_services", "@hl_dom_dirty", "@hl_dom_lab"):
        require(token in manager, "canonical domain token missing: %s" % token)
    for geometry in (
        'panel.set_size_request(500, 560)',
        'panel.set_size_request(1180, 760)',
        'rail.set_size_request(170, -1)',
        'self.inspect_holder.set_size_request(300, -1)',
    ):
        require(geometry in manager, "definitive mockup geometry missing: %s" % geometry)

    foot = text("roles/host_desktop_sway/files/foot.ini")
    require("include=~/.config/hyperlab/palette-foot.ini" in foot,
            "Foot is disconnected from the runtime-selected palette")
    require("[colors]" not in foot and "[cursor]" not in foot,
            "Foot main config reintroduced obsolete colour sections")
    for variant in ("green", "violet", "blue", "red"):
        palette_foot = text(
            f"roles/host_desktop_sway/files/palette/{variant}/hyperlab-palette-foot.ini"
        )
        require("[colors-dark]" in palette_foot,
                f"{variant} Foot palette is not using 1.26 colors-dark syntax")
        require("alpha=0.72" in palette_foot,
                f"{variant} transparent HyperLab terminal alpha missing")
        require(re.search(r"(?m)^cursor=\S+\s+\S+$", palette_foot) is not None,
                f"{variant} Foot cursor is not a parse-clean colour pair")
    rofi_compat = text("roles/host_desktop_sway/files/rofi-mocha.rasi")
    require('@import "~/.config/hyperlab/palette.rasi"' in rofi_compat,
            "Rofi is disconnected from the runtime-selected palette")
    require("accent2:     @hl-accent2;" in rofi_compat,
            "Rofi secondary accent is disconnected from the palette")
    for rofi_path in ("roles/host_desktop_sway/files/rofi-launcher.rasi",
                      "roles/host_desktop_sway/files/rofi-hyperlab.rasi"):
        rofi_theme = text(rofi_path)
        require("background-color: @base;" in rofi_theme,
                f"{rofi_path} does not use the active palette base")
        require("#1e1e2e" not in rofi_theme and "#181825" not in rofi_theme,
                f"{rofi_path} contains a stale hard-coded Violet surface")

    for ly_marker in (
        'animation, value: "colormix"',
        'bigclock, value: "en"',
        'initial_info_text, value: "HyperLab secure console"',
        'start_cmd, value: "/etc/ly/hyperlab-startup.sh"',
        "ly-hyperlab-startup.sh.j2",
    ):
        require(ly_marker in tasks, f"Ly visual contract missing: {ly_marker}")
    ly_startup = text("roles/host_desktop_sway/templates/ly-hyperlab-startup.sh.j2")
    require("\\033]P0" in ly_startup and "\\033]PF" in ly_startup,
            "Ly virtual-terminal palette hook is incomplete")

    require("set $filemanager nemo" in sway,
            "Nemo is not the canonical host file manager")
    require("gtk-3.0/gtk.css" in tasks and
            "gtk-4.0/gtk.css" in tasks and
            "hyperlab-palette-gtk.css" in palette_tasks,
            "Nemo cannot inherit the managed HyperLab GTK palette")

    ET.parse(ROOT / "roles/host_desktop_sway/files/hyperlab-control-center.svg")
    for domain in ("clean", "dev", "lab", "dirty", "services"):
        ET.parse(ROOT / ("roles/host_desktop_sway/files/domain-%s.svg" % domain))
        require(('"icon": "/usr/share/icons/hyperlab/domains/%s.svg"' % domain) in manager,
                "manager domain SVG mapping missing: %s" % domain)
    require('Gtk.Image.new_from_file(meta["icon"])' in manager and
            'text_label("◆"' not in manager,
            "text diamonds remain instead of SVG domain cubes")
    ET.parse(ROOT / "roles/host_desktop_sway/files/hyperlab-wallpaper.svg")
    desktop_wallpaper = ROOT / "roles/host_desktop_sway/files/wallpaper-desktop.png"
    lockscreen_wallpaper = ROOT / "roles/host_desktop_sway/files/wallpaper-lockscreen.png"
    require(desktop_wallpaper.is_file() and desktop_wallpaper.stat().st_size > 25000,
            "desktop wallpaper PNG is missing or suspiciously small")
    require(lockscreen_wallpaper.is_file() and lockscreen_wallpaper.stat().st_size > 25000,
            "lockscreen wallpaper PNG is missing or suspiciously small")
    swaylock = text("roles/host_desktop_sway/files/swaylock.conf")
    require("image=" not in swaylock,
            "static lockscreen image bypasses the distinct-image wrapper")
    for variant in ("green", "violet", "blue", "red"):
        for number in range(1, 21):
            wallpaper = ROOT / f"roles/host_desktop_sway/files/wallpapers/{variant}/{number:02d}.png"
            require(wallpaper.is_file() and wallpaper.stat().st_size > 25000,
                    f"wallpaper pool asset missing or suspiciously small: {variant}/{number:02d}")

    render = text("tests/render.yml")
    for marker in (
        "group/hyperlab", "custom/brand",
        "'nemo' in render_desk_pkgs",
        "'set $filemanager nemo' in render_sway",
        "'superfile' not in render_sway",
        "'pipewire-audio' in render_desk_pkgs",
        "'vulkan-intel' in render_desk_pkgs",
        "'intel-media-driver' in render_desk_pkgs",
        "alpha=0.72", "hyperlab-wallpaper.svg",
        "gtk-3.0/gtk.css", "gtk-4.0/gtk.css",
        "background-color: alpha(@hl_base, 0.48);",
    ):
        require(marker in render, "render contract lacks visual marker: %s" % marker)

    print("M11 v8 HyperLab Shell visual-lock contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
