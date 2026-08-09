#!/usr/bin/env python3
"""HyperLab Control Center.

A native GTK4 control plane for the complete laptop lab. Every operation is
resolved by hyperlabctl; this process never assembles a shell command from user
input and never duplicates the policy encoded by the CLI and playbooks.
"""

from __future__ import annotations

import getpass
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ctypes import CDLL

# gtk4-layer-shell must be loaded before GTK/Wayland libraries. Upstream's
# Python example uses this ordering to guarantee that the layer-shell symbols
# are available before libwayland-client is loaded.
_LAYER_SHELL_LIBRARY = CDLL("libgtk4-layer-shell.so")

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402


APP_ID = "io.github.importriri.HyperlabControlCenter"
CLI = "/usr/local/bin/hyperlabctl"
FOOT = "foot"
PYTHON = "/usr/bin/python"
SECTIONS = (
    "overview",
    "domains",
    "vms",
    "create",
    "images",
    "policies",
    "gpu",
    "activity",
    "diagnostics",
)
DOMAIN_META = {
    "clean": {
        "title": "Clean",
        "subtitle": "Verified software and trusted data",
        "detail": "Persistent workloads and personal identities. No implicit transition to less trusted domains.",
        "css": "domain-clean",
        "icon": "/usr/share/icons/hyperlab/domains/clean.svg",
    },
    "dev": {
        "title": "Dev",
        "subtitle": "Development, builds and controlled tools",
        "detail": "Daily environment for code, toolchains and reproducible tests.",
        "css": "domain-dev",
        "icon": "/usr/share/icons/hyperlab/domains/dev.svg",
    },
    "lab": {
        "title": "Lab",
        "subtitle": "Isolated experiments and workloads",
        "detail": "Default boundary for disposable VMs, analysis and VFIO testing.",
        "css": "domain-lab",
        "icon": "/usr/share/icons/hyperlab/domains/lab.svg",
    },
    "dirty": {
        "title": "Dirty",
        "subtitle": "Unverified software",
        "detail": "No clean data. Prefer disposable workloads and validate every outward transfer.",
        "css": "domain-dirty",
        "icon": "/usr/share/icons/hyperlab/domains/dirty.svg",
    },
    "services": {
        "title": "Services",
        "subtitle": "Shared lab services",
        "detail": "Persistent backends. The catalog always excludes VFIO from this domain.",
        "css": "domain-services",
        "icon": "/usr/share/icons/hyperlab/domains/services.svg",
    },
}
PUBLIC_KEY_RE = re.compile(
    r"^(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)|"
    r"sk-ssh-ed25519@openssh\.com|"
    r"sk-ecdsa-sha2-nistp256@openssh\.com) "
    r"[A-Za-z0-9+/]+={0,3}(?: [^\r\n]+)?$"
)
CSS = r"""
window.hyperlab-surface {
    background: transparent;
    color: @hl_text;
    font-family: "JetBrainsMono Nerd Font";
}
.shell-panel {
    background: @hl_base;
    border: 1px solid alpha(@hl_accent2, .28);
    border-radius: 18px;
    box-shadow: 0 12px 34px alpha(#000000, .28);
    color: @hl_text;
}
.overlay-panel { padding: 14px; }
.drawer-panel { padding: 12px; }
.shell-header {
    background: alpha(@hl_mantle, .34);
    border: 1px solid alpha(@hl_accent2, .22);
    border-radius: 14px;
    padding: 9px 11px;
}
.header-title { font-size: 20px; font-weight: 800; color: @hl_text; }
.header-subtitle { color: @hl_subtext; font-size: 11px; }
.header-logo {
    background: alpha(@hl_mantle, .38);
    border: 1px solid alpha(@hl_accent2, .34);
    border-radius: 11px;
    padding: 7px;
}
button {
    color: @hl_text;
    background: alpha(@hl_mantle, .30);
    border: 1px solid alpha(@hl_accent2, .18);
    border-radius: 9px;
    box-shadow: none;
}
button:hover {
    color: @hl_text;
    background: alpha(@hl_surface, .42);
    border-color: alpha(@hl_accent2, .42);
}
button:active {
    background: alpha(@hl_surface, .48);
    border-color: alpha(@hl_accent2, .58);
}
button:disabled {
    color: alpha(@hl_subtext, .55);
    background: alpha(@hl_base, .17);
    border-color: alpha(@hl_overlay, .12);
    opacity: .62;
}
.shell-tabs {
    background: alpha(@hl_base, .20);
    border: 1px solid alpha(@hl_accent2, .17);
    border-radius: 12px;
    padding: 4px;
}
.nav-button {
    padding: 7px 10px;
    border-radius: 8px;
    background: alpha(@hl_mantle, .14);
    color: @hl_subtext;
}
.nav-button:hover { background: alpha(@hl_surface, .34); color: @hl_text; }
.nav-button.active {
    background: alpha(@hl_accent, .24);
    color: @hl_text;
    border: 1px solid alpha(@hl_accent, .48);
    font-weight: 700;
}
.toolbar {
    background: alpha(@hl_base, .18);
    border: 1px solid alpha(@hl_accent2, .15);
    border-radius: 13px;
    padding: 6px;
}
.toolbar-button {
    min-width: 74px;
    min-height: 52px;
    border-radius: 10px;
    background: alpha(@hl_surface, .30);
    color: @hl_text;
    padding: 5px 8px;
}
.toolbar-button:hover { background: alpha(@hl_surface, .38); }
.toolbar-button:disabled { opacity: .48; }
.toolbar-icon { font-size: 17px; color: @hl_accent2; }
.page { padding: 10px 1px 3px; }
.page-title { font-size: 22px; font-weight: 800; color: @hl_text; }
.page-subtitle { color: @hl_subtext; font-size: 12px; margin-bottom: 5px; }
.card {
    background: alpha(@hl_mantle, .29);
    border: 1px solid alpha(@hl_accent2, .16);
    border-radius: 13px;
    padding: 11px;
}
.card:hover { background: alpha(@hl_surface, .35); border-color: alpha(@hl_accent2, .31); }
.card-title { font-size: 14px; font-weight: 700; color: @hl_text; }
.card-subtitle { color: @hl_subtext; font-size: 11px; }
.metric-value { font-size: 25px; font-weight: 800; }
.metric-label { color: @hl_subtext; font-size: 10px; }
.section-title { font-size: 17px; font-weight: 800; margin-top: 4px; color: @hl_text; }
.muted { color: @hl_subtext; }
.caption { color: @hl_subtext; font-size: 10px; }
.status-ready { background: alpha(@hl_ok, .13); color: @hl_ok; border: 1px solid alpha(@hl_ok, .20); border-radius: 999px; padding: 3px 7px; }
.status-blocked { background: alpha(@hl_bad, .12); color: @hl_bad; border: 1px solid alpha(@hl_bad, .18); border-radius: 999px; padding: 3px 7px; }
.status-warn { background: alpha(@hl_warn, .11); color: @hl_warn; border: 1px solid alpha(@hl_warn, .17); border-radius: 999px; padding: 3px 7px; }
.tag { background: alpha(@hl_surface, .34); color: @hl_subtext; border: 1px solid alpha(@hl_accent2, .12); border-radius: 999px; padding: 3px 7px; }
.domain-clean { border-left: 3px solid @hl_dom_clean; }
.domain-dev { border-left: 3px solid @hl_dom_dev; }
.domain-lab { border-left: 3px solid @hl_dom_lab; }
.domain-dirty { border-left: 3px solid @hl_dom_dirty; }
.domain-services { border-left: 3px solid @hl_dom_services; }
.domain-badge-clean { background: alpha(@hl_dom_clean, .12); color: @hl_dom_clean; }
.domain-badge-dev { background: alpha(@hl_dom_dev, .12); color: @hl_dom_dev; }
.domain-badge-lab { background: alpha(@hl_dom_lab, .13); color: @hl_dom_lab; }
.domain-badge-dirty { background: alpha(@hl_dom_dirty, .13); color: @hl_dom_dirty; }
.domain-badge-services { background: alpha(@hl_dom_services, .12); color: @hl_dom_services; }
.domain-cube { min-width: 28px; min-height: 28px; }
.domain-badge-clean, .domain-badge-dev, .domain-badge-lab,
.domain-badge-dirty, .domain-badge-services {
    border-radius: 7px;
    padding: 3px 6px;
    font-weight: 700;
}
.suggested-action {
    background-image: linear-gradient(to right, alpha(@hl_accent, .45), alpha(@hl_accent2, .46));
    color: @hl_text;
    border: 1px solid alpha(@hl_accent2, .40);
    font-weight: 700;
}
.suggested-action:hover {
    background-image: linear-gradient(to right, alpha(@hl_accent, .56), alpha(@hl_accent2, .54));
}
.destructive-action { background: alpha(@hl_bad, .15); color: @hl_bad; border-color: alpha(@hl_bad, .28); }
.warning { background: alpha(@hl_warn, .08); border: 1px solid alpha(@hl_warn, .18); border-radius: 11px; padding: 9px; }
.problem-error { border-left: 3px solid @hl_bad; }
.problem-warn { border-left: 3px solid @hl_warn; }
.problem-ok { border-left: 3px solid @hl_dom_clean; }
.vm-table {
    background: alpha(@hl_base, .18);
    border: 1px solid alpha(@hl_accent2, .15);
    border-radius: 12px;
    padding: 3px;
}
.vm-header {
    background: alpha(@hl_surface, .29);
    border-radius: 9px;
    padding: 7px 8px;
    color: @hl_subtext;
    font-size: 10px;
    font-weight: 700;
}
.vm-row { background: transparent; border-radius: 9px; padding: 7px 8px; }
row:selected .vm-row { background: alpha(@hl_accent, .14); border: 1px solid alpha(@hl_accent2, .24); }
row:hover .vm-row { background: alpha(@hl_surface, .24); }
.table-primary { font-weight: 700; }
.table-secondary { color: @hl_subtext; font-size: 9px; }
.details-pane {
    background: alpha(@hl_base, .18);
    border: 1px solid alpha(@hl_accent2, .15);
    border-radius: 12px;
    padding: 10px;
}
.status-strip { padding: 5px 0 0; }
.status-tile {
    background: alpha(@hl_mantle, .25);
    border: 1px solid alpha(@hl_accent2, .13);
    border-radius: 10px;
    padding: 7px 9px;
}
.drawer-content {
    background: alpha(@hl_base, .13);
    border: 1px solid alpha(@hl_accent2, .12);
    border-radius: 11px;
    padding: 8px;
}
.quick-actions {
    background: alpha(@hl_base, .15);
    border: 1px solid alpha(@hl_accent2, .13);
    border-radius: 11px;
    padding: 6px;
}
.close-button { border-radius: 999px; min-width: 32px; min-height: 32px; }
row, list { background: transparent; }
separator { background: alpha(@hl_accent2, .16); }
entry, dropdown, spinbutton {
    background: alpha(@hl_base, .25);
    color: @hl_text;
    border: 1px solid alpha(@hl_accent2, .24);
    border-radius: 8px;
}
textview { background: alpha(@hl_base, .34); color: @hl_text; font-family: monospace; }
scrollbar trough { background: transparent; }
scrollbar slider { background: alpha(@hl_accent2, .23); border-radius: 999px; min-width: 6px; min-height: 24px; }
tooltip { background: alpha(@hl_base, .96); color: @hl_text; border: 1px solid alpha(@hl_accent2, .26); border-radius: 8px; }
"""


class ControlError(RuntimeError):
    pass


@dataclass
class Model:
    status: dict[str, Any] = field(default_factory=dict)
    catalog: list[dict[str, Any]] = field(default_factory=list)
    domains: list[dict[str, Any]] = field(default_factory=list)
    specs: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    load_errors: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[dict[str, Any]]:
        problems = self.status.get("problems")
        return problems if isinstance(problems, list) else []

    @property
    def ready_images(self) -> list[dict[str, Any]]:
        return [entry for entry in self.catalog if entry.get("ready")]

    @property
    def running_domains(self) -> list[dict[str, Any]]:
        return [item for item in self.domains if str(item.get("state", "")).lower() == "running"]


@dataclass
class SessionEvent:
    title: str
    detail: str
    kind: str = "info"


def run_cli_json(*args: str, allow_nonzero: bool = False) -> Any:
    try:
        result = subprocess.run(
            [CLI, "--json", *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5.0,
        )
    except subprocess.TimeoutExpired as exc:
        raise ControlError("hyperlabctl did not respond within 5 seconds") from exc
    if result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ControlError("hyperlabctl returned invalid JSON") from exc
        if result.returncode == 0 or allow_nonzero:
            return payload
    message = result.stderr.strip() or result.stdout.strip() or "hyperlabctl failed"
    raise ControlError(message)


def resolve(action_id: str, **targets: str | None) -> list[str]:
    args = ["actions", "--resolve", action_id]
    for key, value in targets.items():
        if value is not None:
            args.extend(["--" + key.replace("_", "-"), value])
    payload = run_cli_json(*args)
    if not isinstance(payload, list) or not all(isinstance(part, str) for part in payload):
        raise ControlError("invalid action resolution: %s" % action_id)
    return payload


def terminal_sequence(sequences: list[list[str]], title: str) -> None:
    code = r"""
import json, subprocess, sys
sequences = json.loads(sys.argv[1])
rc = 0
for index, argv in enumerate(sequences, 1):
    print("\n== step %d/%d ==" % (index, len(sequences)))
    print("argv:", json.dumps(argv))
    rc = subprocess.call(argv)
    if rc:
        break
try:
    input("\n[exit %d - press Enter to close] " % rc)
except EOFError:
    pass
raise SystemExit(rc)
"""
    subprocess.Popen(
        [
            FOOT,
            "--app-id=hyperlab-operation",
            "--title=" + title,
            PYTHON,
            "-c",
            code,
            json.dumps(sequences),
        ],
        start_new_session=True,
    )


def launch_argv(argv: list[str]) -> None:
    subprocess.Popen(argv, start_new_session=True)


def public_keys(path: str) -> list[str]:
    candidate = Path(path).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise ControlError("The public key must be a regular file")
    if candidate.stat().st_size > 16384:
        raise ControlError("The public-key file is too large")
    keys: list[str] = []
    for line in candidate.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if PUBLIC_KEY_RE.fullmatch(line) is None:
            raise ControlError("Invalid OpenSSH key: %s" % candidate)
        if line not in keys:
            keys.append(line)
    if not keys:
        raise ControlError("No valid public key in %s" % candidate)
    return keys


def set_css(widget: Gtk.Widget, *classes: str) -> Gtk.Widget:
    for css_class in classes:
        widget.add_css_class(css_class)
    return widget


def text_label(text: str, *classes: str, wrap: bool = True) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0)
    label.set_wrap(wrap)
    label.set_selectable(False)
    set_css(label, *classes)
    return label


def clear_box(box: Gtk.Box) -> None:
    child = box.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


def card(vertical: bool = True, spacing: int = 10) -> Gtk.Box:
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
        spacing=spacing,
    )
    set_css(box, "card")
    return box


def button(label: str, callback: Callable[[Gtk.Button], None], css: str | None = None) -> Gtk.Button:
    item = Gtk.Button(label=label)
    item.connect("clicked", callback)
    if css:
        item.add_css_class(css)
    return item


def dropdown_value(widget: Gtk.DropDown) -> str | None:
    item = widget.get_selected_item()
    return item.get_string() if item is not None else None


class HyperlabWindow(Gtk.Window):
    """One Layer Shell surface: either the Waybar drawer or full manager."""

    def __init__(
        self,
        application: Gtk.Application,
        surface_mode: str = "drawer",
        initial_section: str = "vms",
    ):
        super().__init__(application=application, title="HyperLab Control Center")
        self.surface_mode = surface_mode if surface_mode in {"drawer", "overlay"} else "drawer"
        self.initial_section = initial_section if initial_section in SECTIONS else "vms"
        self.set_decorated(False)
        self.add_css_class("hyperlab-surface")
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "hyperlab-%s" % self.surface_mode)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        # A panel-sized Layer Shell surface avoids the full-screen transparent
        # backdrop that compositors can blur and also prevents a second resize
        # after the content model arrives. Unanchored overlay windows are
        # centered; the compact drawer is anchored only to the top-left.
        if self.surface_mode == "drawer":
            LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
            # A zero exclusive zone makes the compositor place this surface
            # below Waybar's reserved area. Any positive top margin would be
            # added afterwards and create a second gap below the 37 px bar.
            LayerShell.set_margin(self, LayerShell.Edge.TOP, 0)
            LayerShell.set_margin(self, LayerShell.Edge.LEFT, 0)
        LayerShell.set_exclusive_zone(self, 0)
        # Sway gives ON_DEMAND layer surfaces regular click-to-focus semantics,
        # so mapping a warmed drawer would leave keyboard focus on the previous
        # application. Both surfaces must take focus as soon as they are shown
        # so Escape and the keyboard controls work without a preceding click.
        # Hiding the surface releases this exclusive request immediately.
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
        self.model = Model()
        self.last_refresh_monotonic = 0.0
        self.events: list[SessionEvent] = []
        self.nav_buttons: dict[str, Gtk.Button] = {}
        self.builders: dict[str, Callable[[], Gtk.Widget]] = {}
        self.current_section = self.initial_section
        self.drawer_tab = "apps"
        self.loading = False
        self.selected_vm: dict[str, Any] | None = None
        self.create_widgets: dict[str, Gtk.Widget] = {}
        self._grid_columns: dict[int, int] = {}
        self.drawer_holder: Gtk.Box | None = None
        self.status_holder: Gtk.Box | None = None
        self._install_css()
        self._build_shell()
        self._install_shortcuts()
        self._install_close_capture()
        self.refresh()

    def _install_css(self) -> None:
        display = Gdk.Display.get_default()
        self._style_provider = Gtk.CssProvider()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display,
                self._style_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
            )
        self.reload_theme()

    def reload_theme(self) -> None:
        palette = Path.home() / ".config/gtk-4.0/hyperlab-palette.css"
        try:
            palette_css = palette.read_text(encoding="utf-8")
            # One provider makes every resident surface resolve the currently
            # selected palette instead of retaining colors from first startup.
            self._style_provider.load_from_data(
                (palette_css + "\n" + CSS).encode("utf-8")
            )
        except (GLib.Error, OSError) as exc:
            print("HyperLab: GTK palette could not be loaded: %s" % exc, file=sys.stderr)

    def _build_shell(self) -> None:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("shell-panel")
        if self.surface_mode == "drawer":
            panel.add_css_class("drawer-panel")
            panel.set_size_request(500, 560)
            self.set_default_size(500, 560)
            self._build_drawer_shell(panel)
        else:
            panel.add_css_class("overlay-panel")
            panel.set_size_request(1180, 760)
            self.set_default_size(1180, 760)
            self._build_overlay_shell(panel)
        self.set_child(panel)

    def _shell_header(self, compact: bool = False) -> Gtk.Box:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        header.add_css_class("shell-header")
        logo = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/hyperlab-control-center.svg"
        )
        logo.set_pixel_size(26 if compact else 30)
        logo.add_css_class("header-logo")
        header.append(logo)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_box.set_hexpand(True)
        title_box.append(text_label(
            "HyperLab" if compact else "HyperLab Control Center",
            "header-title",
            wrap=False,
        ))
        self.header_status = text_label("Loading status…", "header-subtitle", wrap=False)
        title_box.append(self.header_status)
        header.append(title_box)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text("Refresh the entire lab · Ctrl+R")
        refresh.connect("clicked", lambda _button: self.refresh())
        header.append(refresh)
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("close-button")
        close.set_tooltip_text("Close · Esc")
        close.connect("clicked", lambda _button: self.close_surface())
        header.append(close)
        return header

    def _build_overlay_shell(self, panel: Gtk.Box) -> None:
        panel.append(self._shell_header())
        panel.append(self._build_toolbar())
        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tabs.add_css_class("shell-tabs")
        navigation = [
            ("vms", "Virtual machine"),
            ("create", "Create VM"),
            ("images", "Images"),
            ("domains", "Domains"),
            ("policies", "Networks and policies"),
            ("gpu", "GPU / VFIO"),
            ("activity", "Activity"),
            ("diagnostics", "Diagnostics"),
        ]
        for section, label in navigation:
            nav = Gtk.Button(label=label)
            nav.add_css_class("nav-button")
            nav.connect("clicked", lambda _button, name=section: self.select_section(name))
            tabs.append(nav)
            self.nav_buttons[section] = nav
        panel.append(tabs)

        self.stack = Gtk.Stack()
        # The control plane is operational UI, not a showcase animation. With
        # a fixed window geometry and no crossfade it appears in one frame.
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_transition_duration(0)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        panel.append(self.stack)
        self.builders = {
            "overview": self._build_overview,
            "domains": self._build_domains,
            "vms": self._build_vms,
            "create": self._build_create,
            "images": self._build_images,
            "policies": self._build_policies,
            "gpu": self._build_gpu,
            "activity": self._build_activity,
            "diagnostics": self._build_diagnostics,
        }
        self.status_holder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_holder.add_css_class("status-strip")
        panel.append(self.status_holder)
        self.select_section(self.initial_section)

    def _build_toolbar(self) -> Gtk.Box:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        toolbar.add_css_class("toolbar")
        actions = (
            ("＋", "New VM", lambda: self.select_section("create"), True),
            ("▶", "Start", lambda: self._toolbar_vm_action("start"), True),
            ("■", "Stop", lambda: self._toolbar_vm_action("stop"), True),
            ("▣", "Console", lambda: self._toolbar_vm_action("console"), True),
            ("◉", "Looking Glass", lambda: self._toolbar_vm_action("looking-glass"), True),
            ("◫", "Snapshot", lambda: None, False),
            ("⇩", "Backup", lambda: None, False),
            ("✓", "Validate", lambda: self._toolbar_vm_action("validate"), True),
            ("↻", "Refresh", self.refresh, True),
        )
        for icon, label, callback, enabled in actions:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.append(text_label(icon, "toolbar-icon", wrap=False))
            box.append(text_label(label, "caption", wrap=False))
            item = Gtk.Button(child=box)
            item.add_css_class("toolbar-button")
            item.set_sensitive(enabled)
            if not enabled:
                item.set_tooltip_text("Available in the Snapshot & Backup stage")
            item.connect("clicked", lambda _button, fn=callback: fn())
            toolbar.append(item)
        return toolbar

    def _build_drawer_shell(self, panel: Gtk.Box) -> None:
        """Build the fast, compact Waybar-adjacent drawer.

        The drawer intentionally avoids the full manager's sidebar, toolbar and
        status rail. It is prebuilt during --warm and only maps/unmaps on click.
        """
        panel.append(self._shell_header(compact=True))

        tabs = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tabs.add_css_class("shell-tabs")
        self.drawer_tab_buttons: dict[str, Gtk.Button] = {}
        for tab, label in (("apps", "VMs"), ("system", "System")):
            item = Gtk.Button(label=label)
            item.add_css_class("nav-button")
            item.set_hexpand(True)
            item.connect("clicked", lambda _button, name=tab: self._select_drawer_tab(name))
            tabs.append(item)
            self.drawer_tab_buttons[tab] = item
        panel.append(tabs)

        search = Gtk.SearchEntry()
        search.set_placeholder_text("Filter virtual machines…")
        search.connect("search-changed", lambda item: self._rebuild_drawer(item.get_text()))
        panel.append(search)

        self.drawer_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.drawer_holder.add_css_class("drawer-content")
        self.drawer_holder.set_hexpand(True)
        self.drawer_holder.set_vexpand(True)
        drawer_scroll = Gtk.ScrolledWindow()
        drawer_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        drawer_scroll.set_hexpand(True)
        drawer_scroll.set_vexpand(True)
        drawer_scroll.set_child(self.drawer_holder)
        panel.append(drawer_scroll)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        footer.add_css_class("quick-actions")
        refresh = Gtk.Button(label="Refresh")
        refresh.set_hexpand(True)
        refresh.connect("clicked", lambda _button: self.refresh())
        footer.append(refresh)
        manager = Gtk.Button(label="Full Control Center")
        manager.set_hexpand(True)
        manager.add_css_class("suggested-action")
        manager.connect("clicked", lambda _button: self._open_full_manager("vms"))
        footer.append(manager)
        panel.append(footer)

        self._select_drawer_tab(self._section_to_drawer_tab(self.initial_section))

    def _section_to_drawer_tab(self, section: str) -> str:
        if section in {"diagnostics", "gpu", "policies", "activity", "domains"}:
            return "system"
        return "apps"

    def _select_drawer_tab(self, tab: str) -> None:
        if tab not in {"apps", "system"}:
            tab = "apps"
        self.drawer_tab = tab
        for name, item in self.drawer_tab_buttons.items():
            if name == tab:
                item.add_css_class("active")
            else:
                item.remove_css_class("active")
        self._rebuild_drawer("")

    def _rebuild_drawer(self, query: str = "") -> None:
        if self.drawer_holder is None:
            return
        clear_box(self.drawer_holder)
        normalized = query.casefold().strip()

        if self.drawer_tab == "apps":
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
            title = text_label("Virtual machines", "section-title", wrap=False)
            title.set_hexpand(True)
            header.append(title)
            header.append(text_label(
                "%d running" % len(self.model.running_domains),
                "status-ready" if self.model.running_domains else "tag",
                wrap=False,
            ))
            self.drawer_holder.append(header)

            visible = 0
            for domain in self.model.domains:
                haystack = json.dumps(domain, sort_keys=True).casefold()
                if normalized.startswith("domain:"):
                    expected = normalized.split(":", 1)[1]
                    networks = [domain.get("network"), *(domain.get("networks") or [])]
                    if expected not in networks:
                        continue
                elif normalized and normalized not in haystack:
                    continue
                visible += 1
                self.drawer_holder.append(self._drawer_vm_row(domain))
            if visible == 0:
                self.drawer_holder.append(text_label(
                    "No VMs detected yet. Created guests will appear here automatically.",
                    "warning",
                ))
        else:
            self.drawer_holder.append(text_label("System summary", "section-title", wrap=False))
            self.drawer_holder.append(self._system_summary_card())

            gpu = card()
            gpu.append(text_label("GPU Passthrough", "card-title", wrap=False))
            vfio = [item for item in self.model.domains if item.get("vfio")]
            gpu.append(text_label(
                "%d VFIO VMs · Looking Glass for Windows · SPICE recovery" % len(vfio),
                "caption",
            ))
            gpu_button = Gtk.Button(label="Open GPU diagnostics")
            gpu_button.connect("clicked", lambda _button: self._open_full_manager("gpu"))
            gpu.append(gpu_button)
            self.drawer_holder.append(gpu)

            trust = card()
            trust.append(text_label("Trust & Network", "card-title", wrap=False))
            trust.append(text_label(
                "5 domains · isolated lab · services without VFIO",
                "caption",
            ))
            diagnostics = Gtk.Button(label="Open full diagnostics")
            diagnostics.connect(
                "clicked", lambda _button: self._open_full_manager("diagnostics")
            )
            trust.append(diagnostics)
            self.drawer_holder.append(trust)

    def _drawer_vm_row(self, domain: dict[str, Any]) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        row.add_css_class("card")
        name = str(domain.get("name", "unnamed"))
        network = str(domain.get("network") or (domain.get("networks") or ["-"])[0])
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)
        left.append(text_label(name, "card-title", wrap=False))
        left.append(text_label(
            "%s · %s · %s" % (
                domain.get("state", "unknown"),
                domain.get("device_profile") or ("vfio" if domain.get("vfio") else "standard"),
                domain.get("lifecycle") or "external",
            ),
            "caption",
            wrap=False,
        ))
        row.append(left)
        if network in DOMAIN_META:
            row.append(text_label(network, "domain-badge-%s" % network, wrap=False))
        open_button = Gtk.Button(label="Open")
        open_button.connect("clicked", lambda _button, vm=domain: self._primary_vm_action(vm))
        row.append(open_button)
        select = Gtk.GestureClick()
        select.connect("released", lambda *_args, vm=domain: setattr(self, "selected_vm", vm))
        row.add_controller(select)
        return row

    def _system_summary_card(self) -> Gtk.Box:
        item = card()
        errors = len(self.model.load_errors) + sum(
            1 for problem in self.model.problems if problem.get("severity") == "error"
        )
        item.append(text_label("Host Health", "card-title", wrap=False))
        item.append(text_label("Good" if errors == 0 else "Check diagnostics", "status-ready" if errors == 0 else "status-blocked", wrap=False))
        item.append(text_label("Running VMs: %d" % len(self.model.running_domains), "caption"))
        item.append(text_label("Sealed images: %d/%d" % (len(self.model.ready_images), len(self.model.catalog)), "caption"))
        item.append(text_label("Snapshot/backup: next stage", "caption"))
        return item

    def _open_full_manager(self, section: str) -> None:
        app = self.get_application()
        if hasattr(app, "route"):
            GLib.idle_add(app.route, "overlay", section, False)

    def close_surface(self) -> None:
        # Keep the fully built window and model resident. Reopening only maps an
        # existing surface instead of importing GTK and rebuilding every page.
        self.set_visible(False)

    def _install_close_capture(self) -> None:
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._capture_key)
        self.add_controller(controller)

    def _capture_key(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close_surface()
            return True
        return False

    def _install_shortcuts(self) -> None:
        controller = Gtk.ShortcutController()
        for trigger, callback in (
            ("<Control>r", self.refresh),
            ("<Control>n", lambda: self.select_section("create") if self.surface_mode == "overlay" else self._open_full_manager("create")),
            ("<Control>f", lambda: self.select_section("vms") if self.surface_mode == "overlay" else self._open_full_manager("vms")),
        ):
            controller.add_shortcut(
                Gtk.Shortcut.new(
                    Gtk.ShortcutTrigger.parse_string(trigger),
                    Gtk.CallbackAction.new(lambda *_args, fn=callback: self._run_shortcut(fn)),
                )
            )
        self.add_controller(controller)

    def _run_shortcut(self, callback: Callable[[], None]) -> bool:
        callback()
        return True

    def select_section(self, section: str) -> None:
        if self.surface_mode == "drawer":
            self._select_drawer_tab(self._section_to_drawer_tab(section))
            self.current_section = section
            return
        if section not in SECTIONS:
            section = "vms"
        page = self.stack.get_child_by_name(section)
        if page is None:
            page = self.builders[section]()
            self.stack.add_named(page, section)
        self.stack.set_visible_child_name(section)
        self.current_section = section
        for name, nav in self.nav_buttons.items():
            if name == section:
                nav.add_css_class("active")
            else:
                nav.remove_css_class("active")

    def rebuild_current(self) -> None:
        if self.surface_mode == "drawer":
            self._rebuild_drawer("")
            return
        old = self.stack.get_child_by_name(self.current_section)
        if old is not None:
            self.stack.remove(old)
        self.stack.add_named(self.builders[self.current_section](), self.current_section)
        self.stack.set_visible_child_name(self.current_section)
        self._rebuild_status_strip()

    def _rebuild_status_strip(self) -> None:
        if self.status_holder is None:
            return
        clear_box(self.status_holder)
        values = (
            ("Trust ladder", "5 domains · isolated lab"),
            ("Image validation", "%d/%d sealed" % (len(self.model.ready_images), len(self.model.catalog))),
            ("Snapshots", "M12 · backend planned"),
            ("Backups", "M12 · guest + host"),
            ("Host recovery", "backend pending detection"),
            ("GPU / VFIO", "%d guest VFIO" % sum(1 for item in self.model.domains if item.get("vfio"))),
        )
        for title, detail in values:
            tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            tile.add_css_class("status-tile")
            tile.set_hexpand(True)
            tile.append(text_label(title, "card-title", wrap=False))
            tile.append(text_label(detail, "caption", wrap=False))
            self.status_holder.append(tile)

    def _toolbar_vm_action(self, operation: str) -> None:
        if self.selected_vm is None:
            self.show_error("Select a VM from the table or launcher first.")
            return
        domain = self.selected_vm
        name = str(domain.get("name", ""))
        running = str(domain.get("state", "")).lower() == "running"
        spec_row = self._spec_by_name(name)
        if operation == "console":
            self._vm_action("vm.console", domain)
        elif operation == "looking-glass":
            if not running or not domain.get("vfio"):
                self.show_error("Looking Glass is available only for a running, configured Windows VFIO VM.")
            else:
                self._vm_action("vm.looking-glass", domain)
        elif operation == "start":
            if running:
                self._primary_vm_action(domain)
            elif domain.get("managed") and spec_row:
                self._managed_action("vm.managed-start", domain, spec_row)
            else:
                self._vm_action("vm.start", domain)
        elif operation == "stop":
            if not running:
                self.show_error("The VM is already stopped.")
            elif domain.get("managed") and spec_row:
                self._managed_action("vm.managed-shutdown", domain, spec_row)
            else:
                self._vm_action("vm.stop", domain)
        elif operation == "validate":
            if domain.get("managed") and spec_row:
                self._managed_action("vm.validate", domain, spec_row)
            else:
                self.show_error("Transactional validation requires a VM managed by a HyperLab spec.")

    def _primary_vm_action(self, domain: dict[str, Any]) -> None:
        self.selected_vm = domain
        running = str(domain.get("state", "")).lower() == "running"
        if not running:
            self._toolbar_vm_action("start")
            return
        spec_row = self._spec_by_name(str(domain.get("name", "")))
        spec = spec_row.get("spec") if spec_row else {}
        image = spec_row.get("image") if spec_row else {}
        if domain.get("vfio") and isinstance(image, dict) and image.get("os_family") == "windows" and isinstance(spec, dict) and spec.get("looking_glass"):
            self._vm_action("vm.looking-glass", domain)
        else:
            self._vm_action("vm.console", domain)

    def _page(self, title: str, subtitle: str) -> tuple[Gtk.ScrolledWindow, Gtk.Box]:
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        set_css(content, "page")
        content.append(text_label(title, "page-title", wrap=False))
        content.append(text_label(subtitle, "page-subtitle"))
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(content)
        return scroll, content

    def _grid(self, columns: int = 3, spacing: int = 14) -> Gtk.Grid:
        grid = Gtk.Grid(column_spacing=spacing, row_spacing=spacing)
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(False)
        self._grid_columns[id(grid)] = columns
        return grid

    def _grid_add(self, grid: Gtk.Grid, widget: Gtk.Widget, index: int, width: int = 1) -> None:
        columns = self._grid_columns.get(id(grid), 3)
        grid.attach(widget, index % columns, index // columns, width, 1)

    def _metric(self, value: str, label: str, detail: str = "") -> Gtk.Box:
        item = card()
        item.append(text_label(value, "metric-value", wrap=False))
        item.append(text_label(label, "metric-label", wrap=False))
        if detail:
            item.append(text_label(detail, "caption"))
        return item

    def refresh(self) -> None:
        if self.loading:
            return
        self.loading = True
        self.header_status.set_text("Refreshing the lab…")
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self) -> None:
        model = Model()
        calls = {
            "status": lambda: run_cli_json("status", allow_nonzero=True),
            "catalog": lambda: run_cli_json("catalog"),
            "domains": lambda: run_cli_json("vm", "list"),
            "specs": lambda: run_cli_json("compose", "list"),
            "actions": lambda: run_cli_json("actions"),
        }
        # These reads are independent. Running them concurrently changes the
        # panel latency from the sum of five CLI calls to the slowest call.
        with ThreadPoolExecutor(max_workers=len(calls), thread_name_prefix="hyperlab-read") as pool:
            futures = {pool.submit(callback): key for key, callback in calls.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    value = future.result()
                except (ControlError, OSError) as exc:
                    model.load_errors.append("%s: %s" % (key, exc))
                    value = {} if key == "status" else []
                setattr(model, key, value)
        GLib.idle_add(self._apply_model, model)

    def _apply_model(self, model: Model) -> bool:
        self.model = model
        self.loading = False
        self.last_refresh_monotonic = time.monotonic()
        severity = "ok"
        if model.load_errors or any(p.get("severity") == "error" for p in model.problems):
            severity = "error"
        elif any(p.get("severity") == "warn" for p in model.problems):
            severity = "warn"
        self.header_status.set_text(
            "%s · %d running VMs · %d/%d ready images"
            % (
                "System healthy" if severity == "ok" else "Check diagnostics",
                len(model.running_domains),
                len(model.ready_images),
                len(model.catalog),
            )
        )
        self.events.insert(
            0,
            SessionEvent(
                "Status refreshed",
                "%d VMs, %d images, %d problems"
                % (len(model.domains), len(model.catalog), len(model.problems)),
                severity,
            ),
        )
        self.rebuild_current()
        return False

    def show_error(self, message: str) -> None:
        dialog = Gtk.Dialog(transient_for=self, modal=True, title="HyperLab")
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        area = dialog.get_content_area()
        area.set_margin_top(18)
        area.set_margin_bottom(18)
        area.set_margin_start(18)
        area.set_margin_end(18)
        area.append(text_label(message))
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()

    def confirm(self, title: str, message: str, on_confirm: Callable[[], None]) -> None:
        dialog = Gtk.Dialog(transient_for=self, modal=True, title=title)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Continue", Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_margin_top(18)
        area.set_margin_bottom(18)
        area.set_margin_start(18)
        area.set_margin_end(18)
        area.append(text_label(message))

        def answered(item: Gtk.Dialog, response: int) -> None:
            item.destroy()
            if response == Gtk.ResponseType.OK:
                on_confirm()

        dialog.connect("response", answered)
        dialog.present()

    def exact_confirm(self, name: str, action: str, on_confirm: Callable[[], None]) -> None:
        dialog = Gtk.Dialog(transient_for=self, modal=True, title=action)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        accept = dialog.add_button(action, Gtk.ResponseType.OK)
        accept.add_css_class("destructive-action")
        area = dialog.get_content_area()
        area.set_margin_top(18)
        area.set_margin_bottom(18)
        area.set_margin_start(18)
        area.set_margin_end(18)
        area.set_spacing(10)
        area.append(text_label("Type %s exactly to confirm." % name))
        entry = Gtk.Entry()
        area.append(entry)

        def answered(item: Gtk.Dialog, response: int) -> None:
            value = entry.get_text()
            item.destroy()
            if response == Gtk.ResponseType.OK:
                if value != name:
                    self.show_error("Invalid confirmation. No operation was performed.")
                    return
                on_confirm()

        dialog.connect("response", answered)
        dialog.present()

    def _build_overview(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Overview",
            "The entire lab in one view: host, images, VMs, trust and next actions.",
        )
        metrics = self._grid(4)
        self._grid_add(metrics, self._metric(str(len(self.model.domains)), "Detected VMs", "%d running" % len(self.model.running_domains)), 0)
        self._grid_add(metrics, self._metric(str(len(self.model.ready_images)), "Ready images", "%d blocked" % (len(self.model.catalog) - len(self.model.ready_images))), 1)
        self._grid_add(metrics, self._metric("5", "Security domains", "clean · dev · lab · dirty · services"), 2)
        self._grid_add(metrics, self._metric(str(len(self.model.problems) + len(self.model.load_errors)), "Problems", "open Diagnostics for details"), 3)
        content.append(metrics)

        health = card()
        health.append(text_label("Operational status", "card-title", wrap=False))
        if self.model.load_errors:
            health.append(text_label("Some sources cannot be read.", "status-blocked", wrap=False))
            for error in self.model.load_errors:
                health.append(text_label(error, "caption"))
        elif any(problem.get("severity") == "error" for problem in self.model.problems):
            health.append(text_label("Errors require attention.", "status-blocked", wrap=False))
        elif self.model.problems:
            health.append(text_label("The system reports warnings.", "status-warn", wrap=False))
        else:
            health.append(text_label("The control plane and providers report no problems.", "status-ready", wrap=False))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(button("Create a VM", lambda _button: self.select_section("create"), "suggested-action"))
        actions.append(button("Manage VMs", lambda _button: self.select_section("vms")))
        actions.append(button("Review images", lambda _button: self.select_section("images")))
        actions.append(button("Diagnostics", lambda _button: self.select_section("diagnostics")))
        health.append(actions)
        content.append(health)

        content.append(text_label("Lab topology", "section-title", wrap=False))
        domain_grid = self._grid(5, 10)
        for index, (domain_id, meta) in enumerate(DOMAIN_META.items()):
            item = card()
            item.add_css_class(meta["css"])
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = Gtk.Image.new_from_file(meta["icon"])
            icon.set_pixel_size(34)
            icon.add_css_class("domain-cube")
            heading.append(icon)
            heading.append(text_label(meta["title"], "card-title", wrap=False))
            item.append(heading)
            item.append(text_label(meta["subtitle"], "card-subtitle"))
            count = sum(
                1
                for domain in self.model.domains
                if domain.get("network") == domain_id
                or domain_id in (domain.get("networks") or [])
            )
            item.append(text_label("%d connected VMs" % count, "caption", wrap=False))
            self._grid_add(domain_grid, item, index)
        content.append(domain_grid)

        content.append(text_label("Available images", "section-title", wrap=False))
        images = self._grid(3)
        for index, entry in enumerate(self.model.catalog):
            item = card()
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            top.set_homogeneous(False)
            title = text_label(entry.get("display_name", entry.get("id", "image")), "card-title", wrap=False)
            title.set_hexpand(True)
            top.append(title)
            top.append(text_label("READY" if entry.get("ready") else "BLOCKED", "status-ready" if entry.get("ready") else "status-blocked", wrap=False))
            item.append(top)
            provenance = " · ".join(part for part in (
                entry.get("os_family"),
                "/".join(entry.get("device_profiles") or []),
            ) if part)
            if provenance:
                item.append(text_label(provenance, "card-subtitle"))
            if not entry.get("ready"):
                item.append(text_label(entry.get("blocked_reason") or "image not ready", "caption"))
            self._grid_add(images, item, index)
        if not self.model.catalog:
            content.append(text_label("Catalog unavailable.", "warning"))
        else:
            content.append(images)
        return scroll

    def _build_domains(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Security domains",
            "Understand the lab through trust boundaries, not only VM names.",
        )
        grid = self._grid(2)
        for index, (domain_id, meta) in enumerate(DOMAIN_META.items()):
            item = card()
            item.add_css_class(meta["css"])
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon = Gtk.Image.new_from_file(meta["icon"])
            icon.set_pixel_size(42)
            icon.add_css_class("domain-cube")
            heading.append(icon)
            heading.append(text_label(meta["title"], "page-title", wrap=False))
            item.append(heading)
            item.append(text_label(meta["subtitle"], "card-title"))
            item.append(text_label(meta["detail"], "muted"))
            allowed = []
            for entry in self.model.catalog:
                mapping = entry.get("network_profiles_by_device") or {}
                profiles = [profile for profile, domains in mapping.items() if domain_id in domains]
                if profiles:
                    allowed.append("%s (%s)" % (entry.get("id"), "/".join(profiles)))
            item.append(text_label("Compatible images", "card-title", wrap=False))
            item.append(text_label(", ".join(allowed) if allowed else "No declared images", "caption"))
            if domain_id == "services":
                item.append(text_label("Hard rule: VFIO is never offered.", "warning"))
            self._grid_add(grid, item, index)
        content.append(grid)
        return scroll

    def _spec_by_name(self, name: str) -> dict[str, Any] | None:
        for row in self.model.specs:
            spec = row.get("spec") if isinstance(row, dict) else None
            if isinstance(spec, dict) and spec.get("name") == name:
                return row
        return None

    def _build_vms(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Virtual machine",
            "Qubes-style fleet view: status, image sealing, domain, VFIO, display and lifecycle at a glance.",
        )
        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search VM, image, domain or notes…")
        search.set_hexpand(True)
        filters.append(search)
        domain_filter = Gtk.DropDown.new_from_strings(["all", *DOMAIN_META.keys()])
        lifecycle_filter = Gtk.DropDown.new_from_strings(["all", "permanent", "disposable"])
        device_filter = Gtk.DropDown.new_from_strings(["all", "standard", "vfio"])
        state_filter = Gtk.DropDown.new_from_strings(["all", "running", "stopped", "paused", "blocked"])
        for widget in (domain_filter, lifecycle_filter, device_filter, state_filter):
            filters.append(widget)
        content.append(filters)

        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        table.add_css_class("vm-table")
        widths = (220, 90, 160, 82, 96, 130, 105, 86, 170)
        headers = ("Name", "State", "Image", "Domain", "Device", "Display", "Lifecycle", "Snapshot", "Notes")
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.add_css_class("vm-header")
        for label, width in zip(headers, widths):
            cell = text_label(label, wrap=False)
            cell.set_size_request(width, -1)
            header.append(cell)
        table.append(header)
        vm_list = Gtk.ListBox()
        vm_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        row_domains: dict[int, dict[str, Any]] = {}
        table.append(vm_list)
        content.append(table)

        detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        detail.add_css_class("details-pane")
        detail.append(text_label("Select a VM", "page-title", wrap=False))
        detail.append(text_label(
            "Double-click: start a stopped VM; open virt-viewer for standard/Linux VFIO; open Looking Glass for configured Windows VFIO.",
            "muted",
        ))
        content.append(detail)

        def render_rows(*_args: object) -> None:
            child = vm_list.get_first_child()
            while child is not None:
                following = child.get_next_sibling()
                vm_list.remove(child)
                child = following
            query = search.get_text().casefold().strip()
            domain_value = dropdown_value(domain_filter) or "all"
            lifecycle_value = dropdown_value(lifecycle_filter) or "all"
            device_value = dropdown_value(device_filter) or "all"
            state_value = dropdown_value(state_filter) or "all"
            row_domains.clear()
            for domain in self.model.domains:
                values = self._vm_table_values(domain)
                haystack = " ".join(values).casefold()
                if query and query not in haystack:
                    continue
                if domain_value != "all" and values[3] != domain_value:
                    continue
                if lifecycle_value != "all" and values[6] != lifecycle_value:
                    continue
                if device_value != "all" and values[4] != device_value:
                    continue
                if state_value != "all" and values[1].casefold() != state_value:
                    continue
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                row_box.add_css_class("vm-row")
                for index, (value, width) in enumerate(zip(values, widths)):
                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                    box.set_size_request(width, -1)
                    primary = value
                    secondary = ""
                    if "\n" in value:
                        primary, secondary = value.split("\n", 1)
                    label = text_label(primary, wrap=False)
                    if index == 0:
                        label.add_css_class("table-primary")
                    box.append(label)
                    if secondary:
                        box.append(text_label(secondary, "table-secondary", wrap=False))
                    if index == 3 and primary in DOMAIN_META:
                        label.add_css_class("domain-badge-%s" % primary)
                    row_box.append(box)
                row = Gtk.ListBoxRow(child=row_box)
                row_domains[id(row)] = domain
                vm_list.append(row)
            if not row_domains:
                empty = Gtk.ListBoxRow(child=text_label(
                    "No VM matches the filters. The fleet remains empty until the first real VM is created.",
                    "warning",
                ))
                empty.set_selectable(False)
                vm_list.append(empty)

        def selected(_list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
            if row is None or id(row) not in row_domains:
                return
            domain = row_domains[id(row)]
            self.selected_vm = domain
            self._render_vm_detail(detail, domain)

        def activated(_list: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
            domain = row_domains.get(id(row))
            if domain is not None:
                self._primary_vm_action(domain)

        search.connect("search-changed", render_rows)
        for widget in (domain_filter, lifecycle_filter, device_filter, state_filter):
            widget.connect("notify::selected", render_rows)
        vm_list.connect("row-selected", selected)
        vm_list.connect("row-activated", activated)
        render_rows()
        return scroll

    def _vm_table_values(self, domain: dict[str, Any]) -> tuple[str, ...]:
        name = str(domain.get("name", "unnamed"))
        state = str(domain.get("state", "unknown"))
        spec_row = self._spec_by_name(name)
        spec = spec_row.get("spec") if spec_row else {}
        image = spec_row.get("image") if spec_row else {}
        image_id = "external"
        image_status = "unmanaged"
        os_family = ""
        if isinstance(spec, dict):
            image_id = str(spec.get("image") or image_id)
        if isinstance(image, dict):
            image_id = str(image.get("id") or image.get("display_name") or image_id)
            image_status = "sealed" if image.get("ready") else "blocked"
            os_family = str(image.get("os_family") or "")
        network = str(domain.get("network") or ((domain.get("networks") or ["-"])[0]))
        device = str(domain.get("device_profile") or ("vfio" if domain.get("vfio") else "standard"))
        lifecycle = str(domain.get("lifecycle") or (spec.get("lifecycle") if isinstance(spec, dict) else "external") or "external")
        if device == "vfio" and os_family == "windows" and isinstance(spec, dict) and spec.get("looking_glass"):
            display = "Looking Glass\nSPICE recovery"
        elif device == "vfio":
            display = "GPU / SPICE\nno kvmfr"
        else:
            display = "SPICE\nvirt-viewer"
        notes = str(spec.get("purpose") if isinstance(spec, dict) else "") or ("managed" if domain.get("managed") else "external")
        return (
            "%s\n%s" % (name, os_family or ("managed" if domain.get("managed") else "external")),
            state,
            "%s\n%s" % (image_id, image_status),
            network,
            device,
            display,
            lifecycle,
            "M12\nplanned",
            notes,
        )

    def _render_vm_detail(self, target: Gtk.Box, domain: dict[str, Any]) -> None:
        clear_box(target)
        name = str(domain.get("name", "unnamed"))
        target.append(text_label(name, "page-title", wrap=False))
        target.append(
            text_label(
                "%s · %s · %s"
                % (
                    domain.get("state", "unknown"),
                    domain.get("device_profile") or ("vfio" if domain.get("vfio") else "standard"),
                    "managed" if domain.get("managed") else "external",
                ),
                "page-subtitle",
            )
        )
        facts = card()
        for key in ("memory_mb", "network", "networks", "hostdevs", "lifecycle", "vfio"):
            if key in domain:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                label = text_label(key.replace("_", " ").title(), "muted", wrap=False)
                label.set_hexpand(True)
                row.append(label)
                row.append(text_label(str(domain.get(key)), wrap=False))
                facts.append(row)
        target.append(facts)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_wrap(True) if hasattr(actions, "set_wrap") else None
        actions.append(button("Ispeziona", lambda _button: self._vm_action("vm.inspect", domain)))
        running = str(domain.get("state", "")).lower() == "running"
        spec_row = self._spec_by_name(name)
        if running:
            actions.append(button("Console", lambda _button: self._vm_action("vm.console", domain), "suggested-action"))
            if domain.get("managed") and spec_row:
                actions.append(button("Clean shutdown", lambda _button: self._managed_action("vm.managed-shutdown", domain, spec_row)))
            else:
                actions.append(button("Clean shutdown", lambda _button: self._vm_action("vm.stop", domain)))
        else:
            if domain.get("managed") and spec_row:
                actions.append(button("Start", lambda _button: self._managed_action("vm.managed-start", domain, spec_row), "suggested-action"))
            else:
                actions.append(button("Start", lambda _button: self._vm_action("vm.start", domain), "suggested-action"))
        if domain.get("managed") and spec_row:
            actions.append(button("Validate", lambda _button: self._managed_action("vm.validate", domain, spec_row)))
            spec = spec_row.get("spec") or {}
            image = spec_row.get("image") or {}
            if running and domain.get("vfio") and image.get("os_family") == "windows" and spec.get("looking_glass"):
                actions.append(button("Looking Glass", lambda _button: self._vm_action("vm.looking-glass", domain)))
            if spec.get("lifecycle") == "disposable":
                actions.append(button("Reset", lambda _button: self._destructive_managed("vm.reset", "RESET disposable", domain, spec_row)))
            if running and domain.get("vfio"):
                actions.append(button("Forza stop", lambda _button: self._destructive_managed("vm.force-stop", "FORZA stop", domain, spec_row), "destructive-action"))
            actions.append(button("Distruggi", lambda _button: self._destructive_managed("vm.destroy", "DISTRUGGI VM", domain, spec_row), "destructive-action"))
        target.append(actions)

    def _vm_action(self, action_id: str, domain: dict[str, Any]) -> None:
        try:
            targets = {"domain": str(domain.get("name"))} if action_id not in {"vm.looking-glass"} else {}
            argv = resolve(action_id, **targets)
            if action_id in {"vm.console", "vm.looking-glass"}:
                launch_argv(argv)
            else:
                terminal_sequence([argv], "hyperlab: " + action_id)
            self.events.insert(0, SessionEvent(action_id, str(domain.get("name"))))
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))

    def _managed_action(self, action_id: str, domain: dict[str, Any], spec_row: dict[str, Any]) -> None:
        try:
            argv = resolve(action_id, spec=spec_row.get("path"))
            terminal_sequence([argv], "hyperlab: %s %s" % (action_id, domain.get("name")))
            self.events.insert(0, SessionEvent(action_id, str(domain.get("name"))))
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))

    def _destructive_managed(self, action_id: str, label: str, domain: dict[str, Any], spec_row: dict[str, Any]) -> None:
        name = str(domain.get("name"))
        self.exact_confirm(name, label, lambda: self._managed_action(action_id, domain, spec_row))

    def _build_create(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Create a VM",
            "A guided path through system, isolation, hardware, resources, identity and final review.",
        )
        if not self.model.catalog:
            content.append(text_label("The catalog is unavailable. Refresh or open Diagnostics.", "warning"))
            return scroll
        form = self._grid(2)
        choices = card()
        choices.append(text_label("Configuration", "card-title", wrap=False))
        image = Gtk.DropDown.new_from_strings([entry.get("id", "") for entry in self.model.catalog])
        lifecycle = Gtk.DropDown.new_from_strings([])
        device = Gtk.DropDown.new_from_strings([])
        network = Gtk.DropDown.new_from_strings([])
        resource = Gtk.DropDown.new_from_strings(["minimum", "balanced", "performance"])
        name = Gtk.Entry()
        name.set_placeholder_text("e.g. dev-workstation")
        purpose = Gtk.Entry()
        purpose.set_placeholder_text("e.g. development workstation")
        keys = Gtk.DropDown.new_from_strings(self._ssh_key_paths())
        key_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        key_row.append(text_label("Public SSH key", "card-subtitle", wrap=False))
        key_row.append(keys)
        fields = (
            ("System", image),
            ("Lifecycle", lifecycle),
            ("Hardware", device),
            ("Domain", network),
            ("Resources", resource),
            ("Name", name),
            ("Purpose", purpose),
        )
        for label, widget in fields:
            choices.append(text_label(label, "card-subtitle", wrap=False))
            choices.append(widget)
        choices.append(key_row)
        review = card()
        review.append(text_label("Review", "card-title", wrap=False))
        review_text = text_label("Select an image.", "muted")
        review.append(review_text)
        warning = text_label("", "warning")
        warning.set_visible(False)
        review.append(warning)
        preview = button("Preview spec", lambda _button: self._preview_create())
        create = button("Write spec and create", lambda _button: self._commit_create(), "suggested-action")
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.append(preview)
        buttons.append(create)
        review.append(buttons)
        self._grid_add(form, choices, 0)
        self._grid_add(form, review, 1)
        content.append(form)
        self.create_widgets = {
            "image": image,
            "lifecycle": lifecycle,
            "device": device,
            "network": network,
            "resource": resource,
            "name": name,
            "purpose": purpose,
            "keys": keys,
            "key_row": key_row,
            "review": review_text,
            "warning": warning,
            "create": create,
        }
        image.connect("notify::selected", lambda *_args: self._create_image_changed())
        lifecycle.connect("notify::selected", lambda *_args: self._create_review())
        device.connect("notify::selected", lambda *_args: self._create_device_changed())
        network.connect("notify::selected", lambda *_args: self._create_review())
        resource.connect("notify::selected", lambda *_args: self._create_review())
        name.connect("changed", lambda *_args: self._create_review())
        purpose.connect("changed", lambda *_args: self._create_review())
        keys.connect("notify::selected", lambda *_args: self._create_review())
        self._create_image_changed()
        return scroll

    def _ssh_key_paths(self) -> list[str]:
        ssh = Path.home() / ".ssh"
        if not ssh.is_dir():
            return []
        return [str(path) for path in sorted(ssh.glob("*.pub")) if path.is_file() and not path.is_symlink()]

    def _selected_image(self) -> dict[str, Any] | None:
        if not self.create_widgets:
            return None
        image_id = dropdown_value(self.create_widgets["image"])
        for entry in self.model.catalog:
            if entry.get("id") == image_id:
                return entry
        return None

    def _set_dropdown(self, widget: Gtk.DropDown, values: list[str], preferred: str | None = None) -> None:
        widget.set_model(Gtk.StringList.new(values))
        index = values.index(preferred) if preferred in values else 0
        widget.set_selected(index if values else Gtk.INVALID_LIST_POSITION)

    def _create_image_changed(self) -> None:
        entry = self._selected_image()
        if entry is None:
            return
        defaults = entry.get("defaults") or {}
        self._set_dropdown(self.create_widgets["lifecycle"], list(entry.get("lifecycles") or []), defaults.get("lifecycle"))
        self._set_dropdown(self.create_widgets["device"], list(entry.get("device_profiles") or []), defaults.get("device_profile"))
        self.create_widgets["key_row"].set_visible(bool(entry.get("cloud_init")))
        self._create_device_changed()

    def _create_device_changed(self) -> None:
        entry = self._selected_image()
        device = dropdown_value(self.create_widgets["device"])
        if entry is None or device is None:
            return
        mapping = entry.get("network_profiles_by_device") or {}
        defaults = entry.get("defaults") or {}
        self._set_dropdown(self.create_widgets["network"], list(mapping.get(device) or []), defaults.get("network_profile"))
        self._create_review()

    def _create_review(self) -> None:
        if not self.create_widgets:
            return
        entry = self._selected_image()
        if entry is None:
            return
        lifecycle = dropdown_value(self.create_widgets["lifecycle"])
        device = dropdown_value(self.create_widgets["device"])
        network = dropdown_value(self.create_widgets["network"])
        resource = dropdown_value(self.create_widgets["resource"])
        name = self.create_widgets["name"].get_text().strip()
        ready = bool(entry.get("ready"))
        key_path = dropdown_value(self.create_widgets["keys"])
        valid = ready and bool(name) and bool(lifecycle and device and network and resource)
        if entry.get("cloud_init") and not key_path:
            valid = False
        self.create_widgets["create"].set_sensitive(valid)
        warning = self.create_widgets["warning"]
        if not ready:
            warning.set_text("Blocked image: %s" % (entry.get("blocked_reason") or "not ready"))
            warning.set_visible(True)
        elif entry.get("cloud_init") and not key_path:
            warning.set_text("This image requires a valid ~/.ssh/*.pub key.")
            warning.set_visible(True)
        else:
            warning.set_visible(False)
        transport = "Looking Glass + SPICE recovery" if device == "vfio" and entry.get("os_family") == "windows" else "SPICE loopback, without kvmfr" if device == "vfio" else "console standard"
        self.create_widgets["review"].set_text(
            "Name: %s\nSystem: %s\nLifecycle: %s\nHardware: %s\nDomain: %s\nResources: %s\nDisplay: %s"
            % (name or "—", entry.get("display_name"), lifecycle, device, network, resource, transport)
        )

    def _compose_args(self, dry_run: bool = False) -> tuple[list[str], list[str]]:
        entry = self._selected_image()
        if entry is None or not entry.get("ready"):
            raise ControlError("Select a ready image")
        name = self.create_widgets["name"].get_text().strip()
        if not name:
            raise ControlError("The VM name is required")
        lifecycle = dropdown_value(self.create_widgets["lifecycle"])
        device = dropdown_value(self.create_widgets["device"])
        network = dropdown_value(self.create_widgets["network"])
        resource = dropdown_value(self.create_widgets["resource"])
        purpose = self.create_widgets["purpose"].get_text().strip() or "%s %s %s workload" % (entry.get("id"), lifecycle, device)
        args = [
            "compose", "write",
            "--name", name,
            "--image", str(entry.get("id")),
            "--lifecycle", str(lifecycle),
            "--device-profile", str(device),
            "--network-profile", str(network),
            "--owner", getpass.getuser(),
            "--resource-profile", str(resource),
            "--purpose", purpose,
        ]
        if dry_run:
            args.append("--dry-run")
        keys: list[str] = []
        if entry.get("cloud_init"):
            key_path = dropdown_value(self.create_widgets["keys"])
            if not key_path:
                raise ControlError("No SSH key selected")
            keys = public_keys(key_path)
        return args, keys

    def _preview_create(self) -> None:
        try:
            args, _keys = self._compose_args(dry_run=True)
            payload = run_cli_json(*args)
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))
            return
        dialog = Gtk.Dialog(transient_for=self, modal=True, title="Preview spec")
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        area = dialog.get_content_area()
        area.set_margin_top(12)
        area.set_margin_bottom(12)
        area.set_margin_start(12)
        area.set_margin_end(12)
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        view.get_buffer().set_text(json.dumps(payload, indent=2, ensure_ascii=False))
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(760, 560)
        scroll.set_child(view)
        area.append(scroll)
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()

    def _commit_create(self) -> None:
        try:
            args, keys = self._compose_args(dry_run=False)
            preview_args = [*args, "--dry-run"]
            preview = run_cli_json(*preview_args)
            spec = preview.get("spec") or {}
            summary = "Create %s from %s in domain %s with profile %s?" % (
                spec.get("name"), spec.get("image"), spec.get("network_profile"), spec.get("device_profile")
            )
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))
            return

        def perform() -> None:
            try:
                written = run_cli_json(*args)
                spec_path = written.get("path")
                if not isinstance(spec_path, str):
                    raise ControlError("compose write did not return the spec path")
                create_argv = resolve("vm.create", spec=spec_path)
                if keys:
                    create_argv.extend([
                        "-e",
                        json.dumps({"guest_cloud_init_ssh_public_keys": keys}, separators=(",", ":")),
                    ])
                start_argv = resolve("vm.managed-start", spec=spec_path)
                terminal_sequence([create_argv, start_argv], "hyperlab: create " + str(spec.get("name")))
                self.events.insert(0, SessionEvent("Creation started", str(spec.get("name")), "ok"))
                self.select_section("activity")
            except (ControlError, OSError) as exc:
                self.show_error(str(exc))

        self.confirm("Confirm creation", summary, perform)

    def _build_images(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Images",
            "Readiness, provenance and preparation actions. A VM can be created only from a valid sealed image.",
        )
        grid = self._grid(2)
        for index, entry in enumerate(self.model.catalog):
            item = card()
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            title = text_label(entry.get("display_name", entry.get("id", "image")), "page-title", wrap=False)
            title.set_hexpand(True)
            top.append(title)
            top.append(text_label("READY" if entry.get("ready") else "BLOCKED", "status-ready" if entry.get("ready") else "status-blocked", wrap=False))
            item.append(top)
            # A missing field must not appear on screen as the literal word
            # Omit an absent value instead of showing a misleading "None" row.
            # This applies to every descriptive row in this card.
            provenance = " · ".join(str(value) for value in (
                entry.get("os_family"), entry.get("os_variant")) if value)
            if provenance:
                item.append(text_label(provenance, "card-subtitle"))
            for label, values in (("Lifecycle", entry.get("lifecycles")),
                                  ("Hardware", entry.get("device_profiles"))):
                if values:
                    item.append(text_label("%s: %s" % (label, ", ".join(values)), "caption"))
            mapping = entry.get("network_profiles_by_device") or {}
            if mapping:
                item.append(text_label("Networks: %s" % "; ".join(
                    "%s=%s" % (profile, ",".join(domains))
                    for profile, domains in mapping.items()), "caption"))
            if not entry.get("ready"):
                item.append(text_label(entry.get("blocked_reason") or "Image not ready", "warning"))
            buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            buttons.append(button("Prepare / import", lambda _button, image=entry: self._image_action("image.import", image)))
            buttons.append(button("Validate", lambda _button, image=entry: self._image_action("image.validate", image)))
            item.append(buttons)
            self._grid_add(grid, item, index)
        content.append(grid)
        return scroll

    def _image_action(self, action_id: str, entry: dict[str, Any]) -> None:
        try:
            argv = resolve(action_id, manifest=entry.get("manifest"))
            terminal_sequence([argv], "hyperlab: %s %s" % (action_id, entry.get("id")))
            self.events.insert(0, SessionEvent(action_id, str(entry.get("id"))))
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))

    def _build_policies(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Networks and policies",
            "Effective catalog-derived matrix: what can enter each domain and with which hardware profile.",
        )
        for domain_id, meta in DOMAIN_META.items():
            item = card()
            item.add_css_class(meta["css"])
            item.append(text_label(meta["title"], "card-title", wrap=False))
            rows: list[str] = []
            for entry in self.model.catalog:
                mapping = entry.get("network_profiles_by_device") or {}
                profiles = [profile for profile, domains in mapping.items() if domain_id in domains]
                if profiles:
                    rows.append("%-14s  %s" % (entry.get("id"), ", ".join(profiles)))
            item.append(text_label("\n".join(rows) if rows else "No allowed path", "caption"))
            if domain_id == "services":
                item.append(text_label("Invariant: services never appears in any VFIO allowlist.", "warning"))
            content.append(item)
        return scroll

    def _build_gpu(self) -> Gtk.Widget:
        scroll, content = self._page(
            "GPU and devices",
            "Handoff status and the explicit difference between Windows and Linux paths.",
        )
        grid = self._grid(2)
        host = self.model.status.get("host") if isinstance(self.model.status, dict) else None
        gpu = self.model.status.get("gpu") if isinstance(self.model.status, dict) else None
        current = card()
        current.append(text_label("Current status", "card-title", wrap=False))
        current.append(text_label(json.dumps(gpu or host or {}, indent=2, ensure_ascii=False), "caption"))
        windows = card()
        windows.append(text_label("Windows VFIO", "card-title", wrap=False))
        windows.append(text_label("GPU + HDMI audio · Looking Glass · kvmfr · SPICE loopback for recovery.", "muted"))
        linux = card()
        linux.append(text_label("Linux VFIO", "card-title", wrap=False))
        linux.append(text_label("GPU + HDMI audio · SPICE loopback · no Looking Glass · no kvmfr memory.", "muted"))
        safety = card()
        safety.append(text_label("Boundary hardware", "card-title", wrap=False))
        safety.append(text_label("Lock, trust transaction and GPU return must stay green. An error here blocks publication.", "warning"))
        for index, item in enumerate((current, windows, linux, safety)):
            self._grid_add(grid, item, index)
        content.append(grid)
        return scroll

    def _build_activity(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Activity",
            "Control Center session history. Complete system logs remain available in Diagnostics.",
        )
        if not self.events:
            content.append(text_label("No activity recorded in this session.", "warning"))
        for event in self.events:
            item = card()
            item.add_css_class("problem-error" if event.kind == "error" else "problem-warn" if event.kind == "warn" else "problem-ok")
            item.append(text_label(event.title, "card-title", wrap=False))
            item.append(text_label(event.detail, "caption"))
            content.append(item)
        return scroll

    def _build_diagnostics(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Diagnostics",
            "Problems, providers and technical tools, kept separate from routine VM operations.",
        )
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.append(button("Doctor", lambda _button: self._diagnostic_action("doctor.run"), "suggested-action"))
        actions.append(button("Libvirt logs", lambda _button: self._diagnostic_action("logs.show")))
        actions.append(button("Trust ladder", lambda _button: self._diagnostic_action("trust.show")))
        actions.append(button("Text panel", lambda _button: self._diagnostic_action("panel.open")))
        content.append(actions)
        if not self.model.problems and not self.model.load_errors:
            content.append(text_label("No problems reported by providers.", "status-ready", wrap=False))
        for error in self.model.load_errors:
            item = card()
            item.add_css_class("problem-error")
            item.append(text_label("Source unavailable", "card-title", wrap=False))
            item.append(text_label(error, "caption"))
            content.append(item)
        for problem in self.model.problems:
            severity = problem.get("severity", "warn")
            item = card()
            item.add_css_class("problem-error" if severity == "error" else "problem-warn")
            item.append(text_label(problem.get("id", "problem"), "card-title", wrap=False))
            item.append(text_label(problem.get("message", ""), "muted"))
            item.append(text_label("provider: %s · severity: %s" % (problem.get("provider", "?"), severity), "caption"))
            content.append(item)
        raw = card()
        raw.append(text_label("Status document", "card-title", wrap=False))
        raw.append(text_label("Generated: %s" % self.model.status.get("generated_at", "unavailable"), "caption"))
        raw.append(button("Show JSON in terminal", lambda _button: terminal_sequence([[CLI, "--json", "status"]], "hyperlab: status JSON")))
        content.append(raw)
        return scroll

    def _diagnostic_action(self, action_id: str) -> None:
        try:
            terminal_sequence([resolve(action_id)], "hyperlab: " + action_id)
            self.events.insert(0, SessionEvent(action_id, "diagnostic action"))
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))


class HyperlabApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.windows: dict[str, HyperlabWindow] = {}
        self._held_warm = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_args: self.quit())
        self.add_action(quit_action)

    def do_activate(self) -> None:
        self.route("drawer", "vms", toggle=False)

    def _ensure_window(self, surface: str, section: str) -> HyperlabWindow:
        window = self.windows.get(surface)
        if window is None:
            window = HyperlabWindow(self, surface_mode=surface, initial_section=section)
            window.connect(
                "destroy",
                lambda destroyed, key=surface: self._surface_destroyed(key, destroyed),
            )
            window.set_visible(False)
            self.windows[surface] = window
        return window

    def keep_warm(self) -> None:
        if not self._held_warm:
            self.hold()
            self._held_warm = True
        # The primary Waybar route is the compact drawer. Prebuild only that
        # surface at session start so the common click is immediate.
        self._ensure_window("drawer", "vms")

    def reload_theme(self) -> None:
        for window in self.windows.values():
            window.reload_theme()

    def route(self, surface: str, section: str, toggle: bool = True) -> None:
        self.keep_warm()
        surface = surface if surface in {"drawer", "overlay"} else "drawer"
        section = section if section in SECTIONS else "vms"
        window = self._ensure_window(surface, section)
        same = window.current_section == section and window.get_visible()
        if same and toggle:
            window.close_surface()
            return
        for other_surface, other in self.windows.items():
            if other_surface != surface and other.get_visible():
                other.close_surface()
        window.reload_theme()
        window.select_section(section)
        window.set_visible(True)
        window.present()
        # Present cached content immediately; refresh stale data afterwards.
        if time.monotonic() - window.last_refresh_monotonic > 5.0:
            GLib.timeout_add(120, self._refresh_visible_windows)

    def _refresh_visible_windows(self) -> bool:
        for window in self.windows.values():
            if window.get_visible():
                window.refresh()
        return False

    def _surface_destroyed(self, surface: str, window: Gtk.Window) -> None:
        if self.windows.get(surface) is window:
            del self.windows[surface]

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        arguments = list(command_line.get_arguments())[1:]
        surface = "drawer"
        section = "vms"
        warm_only = False
        reload_theme_only = False
        index = 0
        while index < len(arguments):
            value = arguments[index]
            if value == "--warm":
                warm_only = True
                index += 1
                continue
            if value == "--reload-theme":
                reload_theme_only = True
                index += 1
                continue
            if value == "--surface" and index + 1 < len(arguments):
                surface = arguments[index + 1]
                index += 2
                continue
            if value == "--section" and index + 1 < len(arguments):
                section = arguments[index + 1]
                index += 2
                continue
            command_line.printerr("unknown argument %s\n" % value)
            return 2
        if warm_only:
            self.keep_warm()
            return 0
        if reload_theme_only:
            self.keep_warm()
            self.reload_theme()
            return 0
        if surface not in {"drawer", "overlay"}:
            command_line.printerr("unknown surface %s\n" % surface)
            return 2
        if section not in SECTIONS:
            command_line.printerr("unknown section %s\n" % section)
            return 2
        self.route(surface, section, True)
        return 0


def main(argv: list[str] | None = None) -> int:
    application = HyperlabApplication()
    return application.run(argv or sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
