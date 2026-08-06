#!/usr/bin/env python3
"""Focused M11 v7 Hyperlab Shell visual-lock contract."""

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

    for boundary in (
        'CDLL("libgtk4-layer-shell.so")',
        'gi.require_version("Gdk", "4.0")',
        'gi.require_version("Gtk", "4.0")',
        'gi.require_version("Gtk4LayerShell", "1.0")',
        "LayerShell.init_for_window(self)",
        "LayerShell.Layer.OVERLAY",
        "LayerShell.KeyboardMode.ON_DEMAND",
        "LayerShell.KeyboardMode.EXCLUSIVE",
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
    require('.config/gtk-4.0/hyperlab-palette.css' in manager and
            "self._style_provider.load_from_data" in manager and
            'palette.read_text(encoding="utf-8")' in manager,
            "manager is disconnected from the runtime-selected palette")
    require('background: @hl_base' in manager,
            "opaque non-blurred manager surface missing")
    require('surface-backdrop' not in manager and
            'self.set_child(panel)' in manager,
            "full-screen backdrop returned around the manager")
    require("ThreadPoolExecutor" in manager and "as_completed" in manager and
            "timeout=5.0" in manager,
            "bounded parallel status loading missing")
    require("def keep_warm" in manager and "self.hold()" in manager and
            'value == "--warm"' in manager and
            'self._ensure_window("drawer", "vms")' in manager and
            "self.windows: dict[str, HyperlabWindow]" in manager,
            "prebuilt resident drawer missing")
    require("Gtk.Image.new_from_file(" in manager and
            "/usr/share/icons/hicolor/scalable/apps/hyperlab-control-center.svg" in manager,
            "shared Hyperlab logo is not used by the manager")
    require("Gtk.EventControllerKey()" in manager and
            "Gtk.PropagationPhase.CAPTURE" in manager and
            "keyval == Gdk.KEY_Escape" in manager,
            "single-Escape close capture missing")
    require("self.set_visible(False)" in manager and
            "def close_surface" in manager,
            "resident hide/reopen close path missing")
    require('for other_surface, other in self.windows.items()' in manager and
            'window.present()' in manager and
            'GLib.timeout_add(120, self._refresh_visible_windows)' in manager,
            "resident drawer/overlay switching is not immediate")
    require('surface = "drawer"' in manager,
            "the no-argument HyperLab route is not the compact drawer")
    require("def _build_quick_actions" not in manager and ".quick-button" not in manager,
            "obsolete oversized drawer quick actions remain in runtime code")
    for tab in ("VMs", "System"):
        require('"%s"' % tab in manager, "drawer tab missing: %s" % tab)
    for heading in (
        "Name", "State", "Image", "Domain", "Device", "Display",
        "Lifecycle", "Snapshot", "Notes",
    ):
        require('"%s"' % heading in manager,
                "Qubes-style table column missing: %s" % heading)
    for capability in (
        "Looking Glass", "GPU Passthrough", "Image validation", "Host recovery",
        "SPICE recovery", "no kvmfr", "Snapshot", "Backup", "disposable",
    ):
        require(capability in manager, "Hyperlab capability missing: %s" % capability)
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
    for package in ("gtk4", "gtk4-layer-shell", "python-gobject", "virt-viewer", "superfile"):
        require("  - %s\n" % package in defaults,
                "desktop package missing: %s" % package)
    require("host_desktop_sway_removed_packages:\n  - yazi\n" in defaults,
            "Yazi removal policy missing")

    tasks = text("roles/host_desktop_sway/tasks/main.yml")
    palette_tasks = text("roles/host_desktop_sway/tasks/palette.yml")
    for deployed in (
        "superfile-config.toml", "hyperlab-gtk.css",
        "hyperlab-wallpaper.svg", "hyperlab-control-center.svg",
        "privatestack-hyperlab-domains.py", "privatestack-waybar.sh",
        "privatestack-fullscreen.sh", "privatestack-theme.sh",
        "privatestack-keyboard.sh", "privatestack-controls.sh",
        "privatestack-swaylock.sh", "privatestack-swaybar-status.py",
    ):
        require(deployed in tasks, "visual-lock asset not deployed: %s" % deployed)
    require("superfile-theme.toml" not in tasks,
            "main desktop tasks still own the active Superfile theme")
    require("superfile/theme/hyperlab.toml" in palette_tasks,
            "runtime palette does not own the Superfile theme destination")
    require("Install every runtime palette fragment" in palette_tasks and
            "Install the selected palette into user-owned active files" in palette_tasks and
            "hyperlab-palette-superfile.toml" in palette_tasks,
            "runtime palettes are not installed into read-only pools and active user files")
    require("/usr/share/icons/hyperlab/domains" in tasks and
            "Deploy the Qubes-style domain cube icons" in tasks,
            "domain cube deployment is missing")
    require("/usr/share/backgrounds/privatestack/hyperlab.svg" in tasks,
            "editable vector wallpaper is not installed")
    require("gtk-3.0/gtk.css" in tasks and "gtk-4.0/gtk.css" in tasks,
            "global Hyperlab GTK theme is not deployed to GTK3 and GTK4")

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
            "Mod+d does not select the Hyperlab Rofi theme explicitly")
    # The geometry moved out of the binding and into the launcher, which clamps
    # it to the focused output instead of assuming one screen size. The
    # invariant is that Mod+Shift+f reaches the single-instance launcher.
    require("set $filemanager /usr/local/bin/privatestack-superfile" in sway,
            "Superfile is launched directly instead of through its launcher")
    require("bindsym $mod+o exec /usr/local/bin/privatestack-opacity-toggle" in sway,
            "Mod+o does not reach the opacity toggle")
    for direction in ("Left", "Down", "Up", "Right"):
        require("bindsym $mod+Shift+%s move %s" % (direction, direction.lower()) in sway,
                "physical arrow move binding missing: %s" % direction)
    for opacity in (
        'for_window [app_id="^foot$"] opacity 0.82',
        'for_window [app_id="^floatterm$"] opacity 0.80',
        'for_window [app_id="^superfile$"] opacity 0.88',
        'for_window [app_id="^hyperlab-operation$"] opacity 0.84',
    ):
        require(opacity in sway, "transparent Sway rule missing: %s" % opacity)
    # This assertion used to forbid `resize set` because it overrode
    # Foot's `--window-size-chars`. That flag is gone: privatestack-superfile now
    # chooses the geometry and limits it to the active output. The for_window rule
    # remains as a safety net if the script cannot resize the window.
    require('for_window [app_id="^superfile$"]            floating enable, '
            'resize set 1200 800, move position center' in sway,
            "Superfile floating fallback geometry missing")
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
            "exec_always /usr/local/bin/privatestack-hyperlab-domains --warm" in sway,
            "supervised bar or warm control plane is not active")
    require("exec_always /usr/local/bin/privatestack-theme session-start" in sway and
            "exec_always /usr/local/bin/privatestack-theme daemon" in sway,
            "theme state or wallpaper rotation is not started by Sway")

    # Native fullscreen remains the stable path. Waybar is supervised and
    # automatically falls back to native Swaybar after rapid failures.
    fullscreen = text("roles/host_desktop_sway/files/privatestack-fullscreen.sh")
    require("hyperlab-transparent-fullscreen" in fullscreen,
            "historical fullscreen helper was deleted instead of deactivated")
    superfile_launcher = text("roles/host_desktop_sway/files/privatestack-superfile.sh")
    require("--session" in superfile_launcher and
            "stty size" in superfile_launcher and
            "rows >= min_rows" in superfile_launcher and
            "columns >= min_columns" in superfile_launcher,
            "Superfile launcher does not wait for the real terminal geometry")
    waybar_launcher = text("roles/host_desktop_sway/files/privatestack-waybar.sh")
    require("waybar -l info -c" in waybar_launcher and
            "waybar.log" in waybar_launcher and
            "failures >= 3" in waybar_launcher and
            "native_bar" in waybar_launcher,
            "supervised Waybar fallback contract missing")
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
        '"modules-left": ["custom/brand", "group/hyperlab", "sway/workspaces", "sway/mode"]'
        in waybar,
        "HyperLab/trust controls are not at the far left",
    )
    require('"format": "  HyperLab"' in waybar,
            "Waybar cube brand label missing")
    require('"format": "TRUST {}"' in waybar and
            '"children-class": "trust-detail"' in waybar and
            '"reveal-delay": 40' in waybar,
            "trust hover drawer is not configured")
    require('"modules-right": ["temperature", "custom/keyboard-layout", "custom/controls", "custom/wallpaper-mode", "network", "pulseaudio", "battery", "clock"]' in waybar,
            "right-side module contract is wrong")
    for route in (
        "privatestack-hyperlab-domains --surface drawer --section vms",
        "privatestack-hyperlab-domains --surface drawer --section diagnostics",
    ):
        require(route in waybar, "direct resident drawer route missing: %s" % route)
    require("--surface overlay" not in waybar,
            "Waybar still opens the full Control Center instead of the compact drawer")
    require('window.set_visible(True)' in manager and
            'Gtk.Button(label="Full Control Center")' in manager,
            "resident drawer mapping or explicit full-center escape hatch missing")

    waybar_css = text("roles/host_desktop_sway/files/waybar.css")
    for marker in (
        "background-color: alpha(@hl_mantle, 0.985)",
        "#hyperlab",
        "#custom-brand",
        "#custom-hyperlab",
        "background: alpha(@hl_ok, 0.065)",
        "background: alpha(@hl_dom_lab, 0.22)",
    ):
        require(marker in waybar_css, "Waybar visual-lock marker missing: %s" % marker)
    require("window#waybar.hidden { opacity: 0; }" not in waybar_css,
            "Waybar can still become fully transparent while running")
    require('@import url("palette.css")' in waybar_css,
            "Waybar is disconnected from the runtime-selected user palette")
    require("--reload-theme" in manager and "def reload_theme" in manager,
            "resident manager cannot reload Green/Violet palettes")

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
                f"{variant} transparent Hyperlab terminal alpha missing")
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

    superfile = text("roles/host_desktop_sway/files/superfile-config.toml")
    require('theme = "hyperlab"' in superfile,
            "Superfile custom theme is not selected")
    require("transparent_background = true" in superfile,
            "Superfile background is not transparent")
    require("show_image_preview = false" in superfile,
            "blurred image preview remains enabled")
    require("default_open_file_preview = false" in superfile,
            "preview panel still opens by default")
    theme = text("roles/host_desktop_sway/files/superfile-theme.toml")
    require('gradient_color = ["#7ee787", "#35e4dd"]' in theme,
            "Superfile fallback gradient diverges from Green tokens")
    require('full_screen_bg = "#0c1512"' in theme,
            "Superfile fallback base diverges from Green")
    for variant in ("green", "violet", "blue", "red"):
        variant_theme = text("roles/host_desktop_sway/files/palette/%s/hyperlab-palette-superfile.toml" % variant)
        require("code_syntax_highlight" in variant_theme and "modal_confirm_bg" in variant_theme,
                "Superfile palette is not a complete theme: %s" % variant)

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
        "group/hyperlab", "custom/brand", "superfile/config.toml",
        "superfile/theme/hyperlab.toml", "transparent_background = true",
        "show_image_preview = false", "alpha=0.72", "hyperlab-wallpaper.svg",
        "gtk-3.0/gtk.css", "gtk-4.0/gtk.css", "background-color: alpha(@hl_base, 0.48);",
    ):
        require(marker in render, "render contract lacks visual marker: %s" % marker)

    print("M11 v7 Hyperlab Shell visual-lock contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
