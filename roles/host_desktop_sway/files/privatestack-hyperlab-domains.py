#!/usr/bin/env python3
"""HyperLab Control Center.

A native GTK4 control plane for the complete laptop lab. Every operation is
resolved by hyperlabctl; this process never assembles a shell command from user
input and never duplicates the policy encoded by the CLI and playbooks.
"""

from __future__ import annotations

import getpass
import os
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
NITRO_CONTROL = "/usr/local/bin/hyperlab-nitro-control"
THEME_CONTROL = "/usr/local/bin/privatestack-theme"
DESKTOP_THEMES = ("green", "violet", "blue", "red")
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
    "nitro",
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
CREATE_PRESETS = {
    "arch-minimal": {
        "title": "arch-minimal",
        "detail": "Arch · disposable · standard · dev · minimum",
        "image": "arch",
        "lifecycle": "disposable",
        "device": "standard",
        "network": "dev",
        "resource": "minimum",
        "purpose": "Minimal Linux SSH workload",
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
button.hyperlab-backdrop-catcher,
button.hyperlab-backdrop-catcher:hover,
button.hyperlab-backdrop-catcher:active {
    background: transparent;
    background-image: none;
    border: none;
    box-shadow: none;
    padding: 0;
}
.shell-panel {
    background: @hl_base;
    border: 1px solid alpha(@hl_accent2, .28);
    border-radius: 18px;
    box-shadow: 0 12px 34px alpha(#000000, .28);
    color: @hl_text;
}
.overlay-panel { padding: 12px; }
.drawer-panel {
    padding: 10px;
    border-radius: 0 0 16px 0;
    border-left-width: 0;
    border-top-width: 0;
}
.control-body { margin-top: 8px; }
.control-rail {
    background: alpha(@hl_mantle, .22);
    border: 1px solid alpha(@hl_accent2, .14);
    border-radius: 12px 0 0 12px;
    padding: 9px 7px;
}
.control-workspace {
    background: alpha(@hl_base, .10);
    border: 1px solid alpha(@hl_accent2, .14);
    border-left-width: 0;
    border-radius: 0 12px 12px 0;
    padding: 9px;
}
.rail-button {
    min-height: 34px;
    padding: 6px 10px;
    border-radius: 8px;
    color: @hl_subtext;
    background: transparent;
}
.rail-button:hover { background: alpha(@hl_surface, .30); color: @hl_text; }
.rail-button.active {
    color: @hl_text;
    background: alpha(@hl_accent, .14);
    border: 1px solid alpha(@hl_accent2, .24);
}
.drawer-tabs { margin-top: 1px; }
.drawer-search { margin: 0 1px; }
.drawer-footer {
    background: alpha(@hl_base, .15);
    border: 1px solid alpha(@hl_accent2, .13);
    border-radius: 11px;
    padding: 6px;
}
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
.network-map {
    background: alpha(@hl_base, .11);
    border: 1px solid alpha(@hl_accent2, .12);
    border-radius: 12px;
    padding: 10px;
}
.network-zone { min-height: 138px; }
.network-vm {
    background: alpha(@hl_surface, .19);
    border: 1px solid alpha(@hl_accent2, .09);
    border-radius: 7px;
    padding: 4px 7px;
}
.network-policy-dock {
    border-top: 2px solid alpha(@hl_accent2, .24);
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

/* ========================================================================
 * Definitive HyperLab mockup translation.
 * Geometry and hierarchy mirror the definitive HTML mockup. Domain colours use
 * semantic tokens and never change meaning with the selected global theme.
 * ======================================================================== */
window.hyperlab-surface {
    background: transparent;
    color: @hl_text;
    font-family: "Inter", "Adwaita Sans", "Cantarell", sans-serif;
    font-size: 13.5px;
}
.shell-panel {
    background: @hl_base;
    color: @hl_text;
    border: 1px solid alpha(#ffffff, .13);
    border-radius: 12px;
    box-shadow: 0 26px 70px alpha(#000000, .60);
    padding: 0;
}
.overlay-panel { padding: 0; border-radius: 12px; }
.drawer-panel {
    padding: 0;
    border-radius: 0 0 12px 0;
    border-top-width: 0;
    border-left-width: 0;
}
.mock-titlebar {
    min-height: 42px;
    padding: 10px 14px;
    border-bottom: 1px solid alpha(#ffffff, .09);
    background: transparent;
}
.mock-title {
    font-family: "Inter", "Adwaita Sans", "Cantarell", sans-serif;
    font-size: 14.5px;
    font-weight: 700;
    color: @hl_text;
}
.mock-badge {
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 999px;
    background: alpha(#ffffff, .06);
    color: alpha(@hl_text, .55);
}
.control-body { margin: 0; background: transparent; }
.control-rail {
    min-width: 170px;
    padding: 12px 9px;
    border-right: 1px solid alpha(#ffffff, .09);
    border-radius: 0;
    border-width: 0 1px 0 0;
    background: transparent;
}
.rail-button {
    min-height: 34px;
    margin: 0 0 3px 0;
    padding: 8px 11px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: alpha(@hl_text, .60);
    font-family: "Inter", "Adwaita Sans", "Cantarell", sans-serif;
    font-size: 13px;
    font-weight: 600;
}
.rail-button:hover { background: alpha(#ffffff, .06); color: @hl_text; }
.rail-button.active {
    background: alpha(#ffffff, .10);
    color: @hl_text;
    border-color: alpha(#ffffff, .14);
}
.mock-main {
    padding: 15px 16px 20px;
    background: transparent;
}
.mock-inspect {
    min-width: 300px;
    padding: 14px 14px 20px;
    border-left: 1px solid alpha(#ffffff, .09);
    background: transparent;
}
.mock-kick {
    font-size: 10px;
    font-weight: 700;
    color: alpha(@hl_text, .38);
}
.mock-section {
    margin: 18px 0 10px 0;
}
.mock-section-first { margin-top: 0; }
.mock-section-line {
    min-height: 1px;
    background: alpha(#ffffff, .09);
}
.mock-section-title { font-size: 12.5px; font-weight: 700; color: @hl_text; }
.mock-section-net {
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 10.5px;
    color: alpha(@hl_text, .34);
}
.domain-dot-clean, .domain-dot-dev, .domain-dot-services,
.domain-dot-dirty, .domain-dot-lab { min-width: 9px; min-height: 9px; border-radius: 3px; }
.domain-dot-clean { background: @hl_dom_clean; }
.domain-dot-dev { background: @hl_dom_dev; }
.domain-dot-services { background: @hl_dom_services; }
.domain-dot-dirty { background: @hl_dom_dirty; }
.domain-dot-lab { background: @hl_dom_lab; }

.vm-tile {
    min-height: 148px;
    border-radius: 12px;
    background: alpha(#ffffff, .04);
    border: 1px solid alpha(#ffffff, .09);
    padding: 0;
}
.vm-tile:hover { background: alpha(#ffffff, .055); }
.vm-tile.selected { background: alpha(#ffffff, .075); }
.vm-tile.domain-clean:hover, .vm-tile.domain-clean.selected { border-color: alpha(@hl_dom_clean, .75); }
.vm-tile.domain-dev:hover, .vm-tile.domain-dev.selected { border-color: alpha(@hl_dom_dev, .75); }
.vm-tile.domain-services:hover, .vm-tile.domain-services.selected { border-color: alpha(@hl_dom_services, .75); }
.vm-tile.domain-dirty:hover, .vm-tile.domain-dirty.selected { border-color: alpha(@hl_dom_dirty, .75); }
.vm-tile.domain-lab:hover, .vm-tile.domain-lab.selected { border-color: alpha(@hl_dom_lab, .75); }
.vm-thumb {
    min-height: 72px;
    padding: 8px 9px;
    border-radius: 12px 12px 0 0;
    background: alpha(#09101a, .82);
}
.vm-thumb.domain-clean { background: alpha(@hl_dom_clean, .10); }
.vm-thumb.domain-dev { background: alpha(@hl_dom_dev, .10); }
.vm-thumb.domain-services { background: alpha(@hl_dom_services, .10); }
.vm-thumb.domain-dirty { background: alpha(@hl_dom_dirty, .10); }
.vm-thumb.domain-lab { background: alpha(@hl_dom_lab, .10); }
.vm-screen {
    min-height: 46px;
    margin: 4px 6px 0 6px;
    padding: 7px;
    border-radius: 5px;
    background: alpha(#04080e, .50);
    border: 1px solid alpha(#ffffff, .18);
}
.vm-screen-line { min-height: 4px; border-radius: 2px; background: alpha(#ffffff, .13); }
.vm-state {
    font-size: 9px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
    background: alpha(#04080e, .62);
}
.vm-state.running.domain-clean { color: @hl_dom_clean; border: 1px solid alpha(@hl_dom_clean, .45); }
.vm-state.running.domain-dev { color: @hl_dom_dev; border: 1px solid alpha(@hl_dom_dev, .45); }
.vm-state.running.domain-services { color: @hl_dom_services; border: 1px solid alpha(@hl_dom_services, .45); }
.vm-state.running.domain-dirty { color: @hl_dom_dirty; border: 1px solid alpha(@hl_dom_dirty, .45); }
.vm-state.running.domain-lab { color: @hl_dom_lab; border: 1px solid alpha(@hl_dom_lab, .45); }
.vm-state.stopped { color: alpha(@hl_text, .46); }
.vm-quick { margin: 4px 0 0 0; }
.quick-button {
    min-height: 24px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid alpha(#ffffff, .20);
    background: alpha(#050910, .74);
    color: @hl_text;
    font-size: 11px;
    font-weight: 700;
}
.quick-button:hover { background: alpha(#ffffff, .12); }
.vm-meta { padding: 10px 12px 12px; }
.vm-name { font-size: 13.5px; font-weight: 700; color: @hl_text; }
.vm-facts {
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 10.5px;
    color: alpha(@hl_text, .40);
}
.new-vm-tile {
    min-height: 148px;
    border-radius: 12px;
    border: 1px dashed alpha(#ffffff, .16);
    background: transparent;
    color: alpha(@hl_text, .48);
    font-weight: 600;
}
.new-vm-tile:hover { color: @hl_text; border-color: alpha(#ffffff, .34); }

.inspect-title { font-size: 17px; font-weight: 800; color: @hl_text; }
.inspect-subtitle {
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 11px;
    color: alpha(@hl_text, .42);
    margin-bottom: 10px;
}
.mock-group { margin-bottom: 16px; }
.mock-group-title { margin-bottom: 8px; }
.pill-button {
    min-height: 30px;
    padding: 7px 12px;
    border-radius: 999px;
    background: alpha(#ffffff, .055);
    border: 1px solid alpha(#ffffff, .13);
    color: alpha(@hl_text, .84);
    font-size: 12px;
    font-weight: 600;
}
.pill-button:hover { background: alpha(#ffffff, .11); color: @hl_text; }
.pill-button.primary { background: alpha(@hl_text, .90); color: @hl_base; border-color: transparent; }
.pill-button.danger { color: #ff9d45; border-color: alpha(#ff9d45, .34); }
.pill-button:disabled { opacity: .34; }
.new-chip {
    font-size: 9px;
    font-weight: 700;
    color: #ff9d45;
    border: 1px solid alpha(#ff9d45, .45);
    border-radius: 999px;
    padding: 2px 6px;
}
.kv-row { padding: 6px 0; border-bottom: 1px solid alpha(#ffffff, .055); }
.kv-key { color: alpha(@hl_text, .48); font-size: 12.5px; }
.kv-value {
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    font-weight: 600;
    color: @hl_text;
}
.mock-why { font-size: 11.5px; color: alpha(@hl_text, .42); }
.mock-why.warning { color: #ff9d45; }

.steps { margin-bottom: 16px; }
.step {
    padding: 9px 11px;
    border-radius: 8px;
    background: alpha(#ffffff, .035);
    border: 1px solid alpha(#ffffff, .08);
}
.step.done { border-color: alpha(#ffffff, .24); }
.step.now { background: alpha(#ffffff, .09); border-color: alpha(#ffffff, .30); }
.step-number { font-family: "JetBrains Mono", monospace; font-size: 9.5px; color: alpha(@hl_text, .30); }
.step-label { font-size: 11.5px; font-weight: 700; color: alpha(@hl_text, .50); }
.step-value { font-family: "JetBrains Mono", monospace; font-size: 10.5px; color: alpha(@hl_text, .32); }
.step.done .step-label, .step.done .step-value, .step.now .step-label { color: @hl_text; }
.options-grid { margin-bottom: 16px; }
.option-card {
    min-height: 66px;
    padding: 11px 12px;
    border-radius: 12px;
    background: alpha(#ffffff, .04);
    border: 1px solid alpha(#ffffff, .10);
    color: @hl_text;
}
.option-card:hover { background: alpha(#ffffff, .075); }
.option-card.selected { background: alpha(#ffffff, .11); border-color: alpha(@hl_text, .50); }
.option-card:disabled { opacity: .36; }
.option-title { font-size: 13px; font-weight: 700; color: @hl_text; }
.option-detail { font-size: 11px; color: alpha(@hl_text, .44); }
.field-label { margin-bottom: 5px; }
entry, dropdown > button {
    min-height: 34px;
    padding: 8px 11px;
    border-radius: 8px;
    color: @hl_text;
    background: alpha(#ffffff, .05);
    border: 1px solid alpha(#ffffff, .13);
}
.preview-spec {
    font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
    font-size: 10.5px;
    padding: 10px 12px;
    border-radius: 8px;
    background: alpha(#000000, .34);
    border: 1px solid alpha(#ffffff, .10);
    color: alpha(@hl_text, .62);
}

.network-canvas { margin: 0 0 10px 0; background: transparent; }
.network-zone {
    border-radius: 12px;
    background: alpha(#ffffff, .025);
    border: 1px solid alpha(#ffffff, .09);
    padding: 7px 11px;
}
.network-zone.domain-clean { border-color: alpha(@hl_dom_clean, .30); background: alpha(@hl_dom_clean, .06); }
.network-zone.domain-dev { border-color: alpha(@hl_dom_dev, .30); background: alpha(@hl_dom_dev, .06); }
.network-zone.domain-services { border-color: alpha(@hl_dom_services, .30); background: alpha(@hl_dom_services, .06); }
.network-zone.domain-dirty { border-color: alpha(@hl_dom_dirty, .30); background: alpha(@hl_dom_dirty, .06); }
.network-zone.domain-lab { border-color: alpha(@hl_dom_lab, .30); background: alpha(@hl_dom_lab, .06); }
.network-node {
    margin-top: 7px;
    padding: 7px 10px;
    border-radius: 8px;
    background: alpha(@hl_base, .90);
    border: 1px solid alpha(#ffffff, .18);
}
.network-node:hover { background: alpha(#ffffff, .08); }
.network-node.selected.domain-clean { border-color: @hl_dom_clean; }
.network-node.selected.domain-dev { border-color: @hl_dom_dev; }
.network-node.selected.domain-services { border-color: @hl_dom_services; }
.network-node.selected.domain-dirty { border-color: @hl_dom_dirty; }
.network-node.selected.domain-lab { border-color: @hl_dom_lab; }
.network-node-title { font-size: 12px; font-weight: 700; }
.network-node-sub { font-family: "JetBrains Mono", monospace; font-size: 9.5px; color: alpha(@hl_text, .36); }
.network-dock {
    margin-top: 10px;
    padding: 12px 14px;
    border-radius: 12px;
    background: alpha(#ffffff, .035);
    border: 1px solid alpha(#ffffff, .09);
}

.gpu-rung {
    min-width: 560px;
    padding: 12px 14px;
    margin-bottom: 8px;
    border-radius: 12px;
    background: alpha(#ffffff, .035);
    border: 1px solid alpha(#ffffff, .09);
}
.gpu-rung.current { border-color: alpha(@hl_text, .40); background: alpha(#ffffff, .075); }
.rung-number {
    min-width: 26px; min-height: 26px;
    border-radius: 999px;
    background: alpha(#ffffff, .09);
    color: alpha(@hl_text, .60);
    font-family: "JetBrains Mono", monospace;
    font-size: 12px;
    font-weight: 700;
}
.gpu-rung.current .rung-number { background: alpha(@hl_text, .88); color: @hl_base; }
.domain-chip {
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12.5px;
    font-weight: 600;
    background: alpha(#ffffff, .05);
}
.domain-chip-clean { border: 1px solid alpha(@hl_dom_clean, .45); color: @hl_dom_clean; background: alpha(@hl_dom_clean, .12); }
.domain-chip-dev { border: 1px solid alpha(@hl_dom_dev, .45); color: @hl_dom_dev; background: alpha(@hl_dom_dev, .12); }
.domain-chip-services { border: 1px solid alpha(@hl_dom_services, .45); color: @hl_dom_services; background: alpha(@hl_dom_services, .12); }
.domain-chip-dirty { border: 1px solid alpha(@hl_dom_dirty, .45); color: @hl_dom_dirty; background: alpha(@hl_dom_dirty, .12); }
.domain-chip-lab { border: 1px solid alpha(@hl_dom_lab, .45); color: @hl_dom_lab; background: alpha(@hl_dom_lab, .12); }
.rung-hold { font-family: "JetBrains Mono", monospace; font-size: 10.5px; color: alpha(@hl_text, .46); }

/* Immutable semantic colours from the definitive mockup. */
.domain-badge-clean { background: alpha(@hl_dom_clean, .12); color: @hl_dom_clean; }
.domain-badge-dev { background: alpha(@hl_dom_dev, .12); color: @hl_dom_dev; }
.domain-badge-services { background: alpha(@hl_dom_services, .12); color: @hl_dom_services; }
.domain-badge-dirty { background: alpha(@hl_dom_dirty, .12); color: @hl_dom_dirty; }
.domain-badge-lab { background: alpha(@hl_dom_lab, .12); color: @hl_dom_lab; }


window.hyperlab-dismiss-surface {
    background: transparent;
}
window.hyperlab-dismiss-surface .shell-panel {
    background: @hl_base;
}
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



def run_nitro_json(*args: str) -> dict[str, Any]:
    # Hardware writes stay behind the reviewed normal-user client. The Control
    # Center never receives sysfs paths or a root-capable command primitive.
    try:
        result = subprocess.run(
            [NITRO_CONTROL, *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=4.0,
        )
    except FileNotFoundError as exc:
        raise ControlError("Nitro runtime client is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ControlError("Nitro runtime broker did not respond within 4 seconds") from exc

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        message = result.stderr.strip() or "Nitro runtime broker returned invalid JSON"
        raise ControlError(message) from exc

    if not isinstance(payload, dict) or type(payload.get("ok")) is not bool:
        raise ControlError("Nitro runtime broker returned an invalid response")
    if not payload["ok"]:
        raise ControlError(str(payload.get("error") or "Nitro runtime request was refused"))

    status = payload.get("status")
    if not isinstance(status, dict):
        raise ControlError("Nitro runtime broker omitted its status payload")
    return status


def run_theme(*args: str) -> str:
    # Theme writes stay in the existing user-owned desktop transaction. Nitro
    # hardware privilege remains isolated behind the separate broker.
    env = os.environ.copy()
    # The resident GTK callback waits for this helper. Suppress only the
    # helper's callback into the same GApplication; the owner reloads all of its
    # cached windows after the helper transaction returns.
    env["HYPERLAB_THEME_SKIP_CONTROL_CENTER_RELOAD"] = "1"
    # A synchronous Sway reload would execute the resident-session supervisor
    # while this GTK callback is still active and replace the visible surface.
    env["HYPERLAB_THEME_DEFER_SWAY_RELOAD"] = "1"
    try:
        result = subprocess.run(
            [THEME_CONTROL, *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=8.0,
            env=env,
        )
    except FileNotFoundError as exc:
        raise ControlError("HyperLab theme controller is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ControlError(
            "HyperLab theme controller did not respond within 8 seconds"
        ) from exc
    if result.returncode != 0:
        message = (
            result.stderr.strip()
            or result.stdout.strip()
            or "HyperLab theme change failed"
        )
        raise ControlError(message)
    return result.stdout.strip()

def resolve(action_id: str, **targets: str | None) -> list[str]:
    args = ["actions", "--resolve", action_id]
    for key, value in targets.items():
        if value is not None:
            args.extend(["--" + key.replace("_", "-"), value])
    payload = run_cli_json(*args)
    if not isinstance(payload, list) or not all(isinstance(part, str) for part in payload):
        raise ControlError("invalid action resolution: %s" % action_id)
    return payload


def hyperlab_checkout() -> str:
    pointer = Path("/etc/hyperlabctl/checkout")
    checkout = pointer.read_text(encoding="utf-8").strip()
    candidate = Path(checkout)
    if not candidate.is_absolute() or not candidate.is_dir():
        raise OSError(
            "invalid HyperLab checkout in /etc/hyperlabctl/checkout"
        )
    return str(candidate)


def terminal_sequence(sequences: list[list[str]], title: str) -> None:
    checkout = hyperlab_checkout()
    code = r"""
import json, subprocess, sys
sequences = json.loads(sys.argv[1])
checkout = sys.argv[2]
rc = 0
for index, argv in enumerate(sequences, 1):
    print("\n== step %d/%d ==" % (index, len(sequences)))
    print("argv:", json.dumps(argv))
    rc = subprocess.call(argv, cwd=checkout)
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
            checkout,
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
        self.add_css_class("hyperlab-dismiss-surface")
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, "hyperlab-%s" % self.surface_mode)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)

        # One Layer Shell surface owns both the visible panel and outside
        # dismissal. Waybar's exclusive zone already removes its 37 px strip.
        for edge in (
            LayerShell.Edge.TOP,
            LayerShell.Edge.RIGHT,
            LayerShell.Edge.BOTTOM,
            LayerShell.Edge.LEFT,
        ):
            LayerShell.set_anchor(self, edge, True)

        LayerShell.set_margin(self, LayerShell.Edge.TOP, 0)
        LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 0)
        LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, 0)
        LayerShell.set_margin(self, LayerShell.Edge.LEFT, 0)
        LayerShell.set_exclusive_zone(self, 0)
        # HyperLab behaves like a desktop popover, not a lock surface.
        # ON_DEMAND keeps keyboard ownership non-exclusive. Pointer dismissal
        # is handled independently from compositor keyboard focus.
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
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
        self.nitro_widgets: dict[str, Gtk.Widget] = {}
        self._grid_columns: dict[int, int] = {}
        self.drawer_holder: Gtk.Box | None = None
        self.status_holder: Gtk.Box | None = None
        self.inspect_holder: Gtk.Box | None = None
        self.selected_network = "dev"
        # Theme buttons may update GTK/Waybar immediately, but Sway's palette
        # reload is delayed until this visible surface is intentionally closed.
        self._theme_sway_reload_pending = False
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
        root = Gtk.Overlay()
        root.set_hexpand(True)
        root.set_vexpand(True)

        catcher = Gtk.Button()
        catcher.set_hexpand(True)
        catcher.set_vexpand(True)
        catcher.set_can_focus(False)
        catcher.add_css_class("hyperlab-backdrop-catcher")
        catcher.connect(
            "clicked",
            lambda *_args: self.close_surface(),
        )
        root.set_child(catcher)

        panel = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        panel.add_css_class("shell-panel")
        panel.set_valign(Gtk.Align.START)

        if self.surface_mode == "drawer":
            panel.add_css_class("drawer-panel")
            panel.set_size_request(500, 560)
            panel.set_halign(Gtk.Align.START)
            panel.set_margin_top(0)
            panel.set_margin_start(0)
            self._build_drawer_shell(panel)
        else:
            panel.add_css_class("overlay-panel")
            panel.set_size_request(1180, 760)
            panel.set_halign(Gtk.Align.CENTER)
            panel.set_margin_top(40)
            self._build_overlay_shell(panel)

        root.add_overlay(panel)
        self.set_child(root)

    def _shell_header(self, compact: bool = False) -> Gtk.Box:
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        header.add_css_class("mock-titlebar")
        header.append(text_label("Machines" if compact else "HyperLab", "mock-title", wrap=False))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)
        self.header_status = text_label("Loading…", "mock-badge", wrap=False)
        header.append(self.header_status)
        if not compact:
            host = self.model.status.get("host") if isinstance(self.model.status, dict) else None
            host_name = "Nitro 5" if not host else str(host.get("model") or host.get("hostname") or "Nitro 5") if isinstance(host, dict) else "Nitro 5"
            self.header_host = text_label(host_name, "mock-badge", wrap=False)
            header.append(self.header_host)
        return header

    def _build_overlay_shell(self, panel: Gtk.Box) -> None:
        panel.append(self._shell_header())

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        body.add_css_class("control-body")
        body.set_hexpand(True)
        body.set_vexpand(True)

        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        rail.add_css_class("control-rail")
        rail.set_size_request(170, -1)
        navigation = [
            ("vms", "Machines"),
            ("create", "Create"),
            ("policies", "Networks"),
            ("gpu", "GPU"),
            ("nitro", "Nitro"),
        ]
        for section, label in navigation:
            nav = Gtk.Button(label=label)
            nav.add_css_class("rail-button")
            nav.connect("clicked", lambda _button, name=section: self.select_section(name))
            rail.append(nav)
            self.nav_buttons[section] = nav
        body.append(rail)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_transition_duration(0)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.add_css_class("mock-main")

        self.inspect_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.inspect_holder.add_css_class("mock-inspect")
        self.inspect_holder.set_size_request(300, -1)
        self.inspect_holder.set_vexpand(True)

        body.append(self.stack)
        body.append(self.inspect_holder)
        panel.append(body)

        # Only these five sections exist in the definitive Control Center rail.
        # Legacy CLI routes remain accepted but collapse into Machines rather
        # than reintroducing a second information architecture.
        # Keep every historical builder available to the display-free test
        # harness and CLI aliases, while exposing only the four definitive
        # mockup sections in the visible rail.
        self.builders = {
            "overview": self._build_overview,
            "domains": self._build_domains,
            "vms": self._build_vms,
            "create": self._build_create,
            "images": self._build_images,
            "policies": self._build_policies,
            "gpu": self._build_gpu,
            "nitro": self._build_nitro,
            "activity": self._build_activity,
            "diagnostics": self._build_diagnostics,
        }
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
        """Definitive 500x560 machine drawer, flush-left under Waybar."""
        panel.append(self._shell_header(compact=True))
        self.drawer_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.drawer_holder.set_hexpand(True)
        self.drawer_holder.set_vexpand(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_child(self.drawer_holder)
        panel.append(scroll)
        self._rebuild_drawer("")

    def _section_to_drawer_tab(self, section: str) -> str:
        return "apps"

    def _select_drawer_tab(self, tab: str) -> None:
        self.drawer_tab = "apps"
        self._rebuild_drawer("")

    def _rebuild_drawer(self, query: str = "") -> None:
        if self.drawer_holder is None:
            return
        clear_box(self.drawer_holder)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_margin_top(12)
        content.set_margin_bottom(16)
        content.set_margin_start(13)
        content.set_margin_end(13)
        content.append(self._build_vm_showcase(columns=2, compact=True))
        self.drawer_holder.append(content)
        if self.header_status is not None:
            self.header_status.set_text("%d running" % len(self.model.running_domains))

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
        running = str(domain.get("state", "")).lower() == "running"
        row.append(text_label(
            "RUNNING" if running else "STOPPED",
            "status-ready" if running else "tag",
            wrap=False,
        ))
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
        self._flush_pending_theme_sway_reload()
        app = self.get_application()
        if hasattr(app, "surface_hidden"):
            app.surface_hidden()

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
            self.current_section = "vms"
            self._rebuild_drawer("")
            return
        aliases = {
            "overview": "vms",
            "domains": "vms",
            "images": "create",
            "activity": "vms",
            "diagnostics": "gpu",
        }
        section = aliases.get(section, section)
        if section not in self.builders:
            section = "vms"
        page = self.stack.get_child_by_name(section)
        if page is None:
            page = self.builders[section]()
            self.stack.add_named(page, section)
        self.stack.set_visible_child_name(section)
        self.current_section = section
        if self.inspect_holder is not None:
            self.inspect_holder.set_visible(section != "policies")
        for name, nav in self.nav_buttons.items():
            if name == section:
                nav.add_css_class("active")
            else:
                nav.remove_css_class("active")

    def rebuild_current(self) -> None:
        if self.surface_mode == "drawer":
            self._rebuild_drawer("")
            return
        if self.current_section not in self.builders:
            self.current_section = "vms"
        old = self.stack.get_child_by_name(self.current_section)
        if old is not None:
            self.stack.remove(old)
        self.stack.add_named(self.builders[self.current_section](), self.current_section)
        self.stack.set_visible_child_name(self.current_section)

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
            if not running or not self._supports_looking_glass(domain):
                self.show_error(
                    "Looking Glass requires a running VFIO VM with an "
                    "approved Looking Glass transport."
                )
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

    def _supports_looking_glass(self, domain: dict[str, Any]) -> bool:
        if not domain.get("vfio"):
            return False

        spec_row = self._spec_by_name(str(domain.get("name", "")))
        if not spec_row:
            return False

        spec = spec_row.get("spec")
        image = spec_row.get("image")

        if not isinstance(spec, dict) or not isinstance(image, dict):
            return False

        if not spec.get("looking_glass"):
            return False

        os_family = str(image.get("os_family") or "")
        mode = str(spec.get("looking_glass_mode") or "")

        return (
            os_family == "windows"
            or mode == "linux-experimental"
        )

    def _supports_ssh(self, domain: dict[str, Any]) -> bool:
        name = str(domain.get("name", ""))
        if not name or str(domain.get("state", "")).lower() != "running":
            return False
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid()))
        inventory = runtime / (name + ".ini")
        return inventory.is_file() and not inventory.is_symlink()

    def _primary_vm_action(self, domain: dict[str, Any]) -> None:
        self.selected_vm = domain
        running = str(domain.get("state", "")).lower() == "running"
        if not running:
            self._toolbar_vm_action("start")
            return
        if self._supports_looking_glass(domain):
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
            "%d running · %d/%d images"
            % (len(model.running_domains), len(model.ready_images), len(model.catalog))
        )
        if hasattr(self, "header_host"):
            host = model.status.get("host") if isinstance(model.status, dict) else None
            if isinstance(host, dict):
                self.header_host.set_text(str(host.get("model") or host.get("hostname") or "Nitro 5"))
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

    def _domain_for_vm(self, domain: dict[str, Any]) -> str:
        network = str(domain.get("network") or ((domain.get("networks") or ["dev"])[0]))
        return network if network in DOMAIN_META else "dev"

    def _mock_section_header(self, domain_id: str, first: bool = False) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("mock-section")
        if first:
            row.add_css_class("mock-section-first")
        dot = Gtk.Box()
        dot.add_css_class("domain-dot-%s" % domain_id)
        row.append(dot)
        row.append(text_label(DOMAIN_META[domain_id]["title"], "mock-section-title", wrap=False))
        row.append(text_label(domain_id, "mock-section-net", wrap=False))
        line = Gtk.Box()
        line.add_css_class("mock-section-line")
        line.set_hexpand(True)
        row.append(line)
        return row

    def _flow_buttons(self) -> Gtk.FlowBox:
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_column_spacing(6)
        flow.set_row_spacing(6)
        flow.set_max_children_per_line(3)
        return flow

    def _mock_pill(self, label: str, callback: Callable[[Gtk.Button], None] | None = None,
                   style: str | None = None, enabled: bool = True) -> Gtk.Button:
        item = Gtk.Button(label=label)
        item.add_css_class("pill-button")
        if style == "primary":
            item.add_css_class("primary")
        elif style == "danger":
            item.add_css_class("danger")
        item.set_sensitive(enabled)
        if callback is not None:
            item.connect("clicked", callback)
        return item

    def _select_vm_tile(self, domain: dict[str, Any]) -> None:
        self.selected_vm = domain
        if self.surface_mode == "drawer":
            self._open_full_manager("vms")
        else:
            self.rebuild_current()

    def _mock_vm_tile(self, domain: dict[str, Any], compact: bool = False) -> Gtk.Box:
        domain_id = self._domain_for_vm(domain)
        name = str(domain.get("name", "unnamed"))
        running = str(domain.get("state", "")).lower() == "running"
        tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        tile.add_css_class("vm-tile")
        tile.add_css_class("domain-%s" % domain_id)
        if getattr(self, "selected_vm", None) and self.selected_vm.get("name") == name:
            tile.add_css_class("selected")

        thumb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        thumb.add_css_class("vm-thumb")
        thumb.add_css_class("domain-%s" % domain_id)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        state = text_label("RUNNING" if running else "STOPPED", "vm-state", "running" if running else "stopped", "domain-%s" % domain_id, wrap=False)
        top.append(state)
        spacer = Gtk.Box(); spacer.set_hexpand(True); top.append(spacer)
        thumb.append(top)
        screen = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        screen.add_css_class("vm-screen")
        for width in (76, 118, 94, 132):
            line = Gtk.Box(); line.add_css_class("vm-screen-line"); line.set_size_request(width, 4); screen.append(line)
        thumb.append(screen)

        quick = Gtk.Revealer()
        quick.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        quick.set_transition_duration(120)
        quick_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        quick_box.add_css_class("vm-quick")
        if running:
            ssh = Gtk.Button(label="SSH")
            ssh.add_css_class("quick-button")
            ssh.set_sensitive(self._supports_ssh(domain))
            ssh.set_tooltip_text(
                "Open the managed guest over the strict runtime SSH inventory"
                if self._supports_ssh(domain)
                else "Runtime SSH inventory is not available for this VM"
            )
            ssh.connect("clicked", lambda _button, vm=domain: self._vm_action("vm.ssh", vm))
            quick_box.append(ssh)
            console = Gtk.Button(label="Console")
            console.add_css_class("quick-button")
            console.connect("clicked", lambda _button, vm=domain: self._vm_action("vm.console", vm))
            quick_box.append(console)
            if self._supports_looking_glass(domain):
                looking_glass = Gtk.Button(label="LG")
                looking_glass.add_css_class("quick-button")
                looking_glass.set_tooltip_text("Looking Glass")
                looking_glass.connect(
                    "clicked",
                    lambda _button, vm=domain:
                    self._vm_action("vm.looking-glass", vm),
                )
                quick_box.append(looking_glass)
        else:
            start = Gtk.Button(label="Start")
            start.add_css_class("quick-button")
            spec_row = self._spec_by_name(name)
            if domain.get("managed") and spec_row:
                start.connect("clicked", lambda _button, vm=domain, row=spec_row: self._managed_action("vm.managed-start", vm, row))
            else:
                start.connect("clicked", lambda _button, vm=domain: self._vm_action("vm.start", vm))
            quick_box.append(start)
        quick.set_child(quick_box)
        thumb.append(quick)
        tile.append(thumb)

        meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        meta.add_css_class("vm-meta")
        meta.append(text_label(name, "vm-name", wrap=False))
        memory = domain.get("memory_mb")
        mem = ("%.0f GiB" % (int(memory) / 1024)) if isinstance(memory, int) and memory else "— GiB"
        vcpus = str(domain.get("vcpus") or domain.get("vcpu") or "—")
        meta.append(text_label("%s · %s vCPU · %s" % (mem, vcpus, domain_id), "vm-facts", wrap=False))
        tile.append(meta)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_args: quick.set_reveal_child(True))
        motion.connect("leave", lambda *_args: quick.set_reveal_child(False))
        tile.add_controller(motion)
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda *_args, vm=domain: self._select_vm_tile(vm))
        tile.add_controller(gesture)
        return tile

    def _build_vm_showcase(self, columns: int, compact: bool = False) -> Gtk.Box:
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        first = True
        order = ("clean", "dev", "services", "dirty", "lab")
        shown = False
        for domain_id in order:
            machines = [vm for vm in self.model.domains if self._domain_for_vm(vm) == domain_id]
            if not machines:
                continue
            shown = True
            content.append(self._mock_section_header(domain_id, first=first))
            first = False
            grid = Gtk.Grid(column_spacing=11, row_spacing=11)
            grid.set_column_homogeneous(True)
            for index, vm in enumerate(machines):
                grid.attach(self._mock_vm_tile(vm, compact=compact), index % columns, index // columns, 1, 1)
            content.append(grid)
        if not shown:
            content.append(text_label("No machines yet. Open Create to build the first one.", "mock-why"))
        new_grid = Gtk.Grid(column_spacing=11, row_spacing=11)
        new_grid.set_column_homogeneous(True)
        new_vm = Gtk.Button(label="＋  New machine")
        new_vm.add_css_class("new-vm-tile")
        new_vm.connect("clicked", lambda _button: self._open_full_manager("create") if compact else self.select_section("create"))
        new_grid.attach(new_vm, 0, 0, 1, 1)
        content.append(new_grid)
        return content

    def _append_kv(self, target: Gtk.Box, key: str, value: str) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("kv-row")
        label = text_label(key, "kv-key", wrap=False)
        label.set_hexpand(True)
        row.append(label)
        row.append(text_label(value, "kv-value", wrap=False))
        target.append(row)

    def _build_vms(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        showcase = self._build_vm_showcase(columns=4)
        scroll.set_child(showcase)
        inspect_holder = getattr(self, "inspect_holder", None)
        if inspect_holder is not None:
            clear_box(inspect_holder)
            if self.selected_vm is None and self.model.domains:
                self.selected_vm = self.model.domains[0]
            if self.selected_vm is not None:
                self._render_vm_detail(inspect_holder, self.selected_vm)
            else:
                inspect_holder.append(text_label("Select a machine to see actions and details.", "mock-why"))
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
        looking_glass_mode = (
            str(spec.get("looking_glass_mode") or "")
            if isinstance(spec, dict)
            else ""
        )
        if (
            device == "vfio"
            and isinstance(spec, dict)
            and spec.get("looking_glass")
            and os_family == "windows"
        ):
            display = "Looking Glass\nSPICE recovery"
        elif (
            device == "vfio"
            and isinstance(spec, dict)
            and spec.get("looking_glass")
            and looking_glass_mode == "linux-experimental"
        ):
            display = "Looking Glass Linux\nSPICE recovery"
        elif device == "vfio":
            display = "GPU / SPICE\nrecovery"
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
        domain_id = self._domain_for_vm(domain)
        spec_row = self._spec_by_name(name)
        spec = spec_row.get("spec") if spec_row else {}
        image = spec_row.get("image") if spec_row else {}
        image_id = str(spec.get("image") or image.get("id") or "external") if isinstance(spec, dict) and isinstance(image, dict) else "external"
        running = str(domain.get("state", "")).lower() == "running"

        target.append(text_label("SELECTED", "mock-kick", wrap=False))
        target.append(text_label(name, "inspect-title", wrap=False))
        target.append(text_label("%s · %s · %s" % (domain.get("state", "unknown"), domain_id, image_id), "inspect-subtitle"))

        connect = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        connect.add_css_class("mock-group")
        connect.append(text_label("CONNECT", "mock-kick", "mock-group-title", wrap=False))
        connect_flow = self._flow_buttons()
        ssh = self._mock_pill(
            "SSH",
            lambda _button, vm=domain: self._vm_action("vm.ssh", vm),
            enabled=running and self._supports_ssh(domain),
        )
        ssh.set_tooltip_text(
            "Open the managed guest over the strict runtime SSH inventory"
            if running and self._supports_ssh(domain)
            else "Runtime SSH inventory is not available for this VM"
        )
        connect_flow.append(ssh)
        connect_flow.append(self._mock_pill("Console", lambda _button, vm=domain: self._vm_action("vm.console", vm), enabled=running))
        connect_flow.append(self._mock_pill("Looking Glass", lambda _button, vm=domain: self._vm_action("vm.looking-glass", vm), style="primary", enabled=running and self._supports_looking_glass(domain)))
        connect.append(connect_flow)
        target.append(connect)

        power = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        power.add_css_class("mock-group")
        power.append(text_label("POWER", "mock-kick", "mock-group-title", wrap=False))
        flow = self._flow_buttons()
        if running:
            if domain.get("managed") and spec_row:
                shutdown = self._mock_pill(
                    "Shut down",
                    lambda _button, vm=domain, row=spec_row: self._managed_action(
                        "vm.managed-shutdown", vm, row
                    ),
                )
                shutdown.set_tooltip_text(
                    "Graceful guest shutdown · wait until QEMU exits"
                )
                flow.append(shutdown)

                reboot = self._mock_pill(
                    "Reboot",
                    lambda _button, vm=domain, row=spec_row: self._managed_action(
                        "vm.managed-reboot", vm, row
                    ),
                )
                reboot.set_tooltip_text(
                    "Guest OS reboot · QEMU stays running"
                    + (
                        " · VFIO may require Power cycle if the GPU or guest agent does not recover"
                        if domain.get("vfio")
                        else ""
                    )
                )
                flow.append(reboot)
            else:
                flow.append(
                    self._mock_pill(
                        "Shut down",
                        lambda _button, vm=domain: self._vm_action("vm.stop", vm),
                    )
                )
            if domain.get("managed") and spec_row and domain.get("vfio"):
                force_stop = self._mock_pill(
                    "Force stop",
                    lambda _button, vm=domain, row=spec_row: self._destructive_managed(
                        "vm.force-stop", "Force stop", vm, row
                    ),
                    style="danger",
                )
                force_stop.set_tooltip_text(
                    "Stop QEMU immediately · unflushed guest data may be lost"
                )
                flow.append(force_stop)

                power_cycle = self._mock_pill(
                    "Power cycle",
                    lambda _button, vm=domain, row=spec_row: self._destructive_managed(
                        "vm.power-cycle", "Power cycle", vm, row
                    ),
                    style="danger",
                )
                power_cycle.set_tooltip_text(
                    "Replace QEMU · reinitialize VFIO devices · forced stop may lose unflushed guest data"
                )
                flow.append(power_cycle)
        else:
            if domain.get("managed") and spec_row:
                flow.append(self._mock_pill("Start", lambda _button, vm=domain, row=spec_row: self._managed_action("vm.managed-start", vm, row), style="primary"))
            else:
                flow.append(self._mock_pill("Start", lambda _button, vm=domain: self._vm_action("vm.start", vm), style="primary"))
        if domain.get("managed") and spec_row:
            flow.append(self._mock_pill("Validate", lambda _button, vm=domain, row=spec_row: self._managed_action("vm.validate", vm, row)))
            if isinstance(spec, dict) and spec.get("lifecycle") == "disposable":
                flow.append(self._mock_pill("Reset", lambda _button, vm=domain, row=spec_row: self._destructive_managed("vm.reset", "Reset disposable", vm, row)))
            flow.append(self._mock_pill("Destroy", lambda _button, vm=domain, row=spec_row: self._destructive_managed("vm.destroy", "Destroy VM", vm, row), style="danger"))
        power.append(flow)
        if running and domain.get("managed") and spec_row and domain.get("vfio"):
            power.append(
                text_label(
                    "VFIO: Reboot keeps QEMU alive. Use Power cycle if the guest does not recover.",
                    "mock-why",
                    "warning",
                )
            )
        target.append(power)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        details.add_css_class("mock-group")
        details.append(text_label("DETAILS", "mock-kick", "mock-group-title", wrap=False))
        values = (
            ("image", image_id),
            ("lifecycle", str(domain.get("lifecycle") or (spec.get("lifecycle") if isinstance(spec, dict) else "external") or "external")),
            ("device", str(domain.get("device_profile") or ("vfio" if domain.get("vfio") else "standard"))),
            ("memory", "%s MiB" % domain.get("memory_mb") if domain.get("memory_mb") else "—"),
            ("vCPU", str(domain.get("vcpus") or domain.get("vcpu") or "—")),
            ("guest agent", "yes" if domain.get("agent") else "unknown"),
        )
        for key, value in values:
            self._append_kv(details, key, value)
        target.append(details)

    def _vm_action(self, action_id: str, domain: dict[str, Any]) -> None:
        try:
            argv = resolve(action_id, domain=str(domain.get("name")))
            self.close_surface()
            if action_id in {"vm.console", "vm.looking-glass", "vm.ssh"}:
                launch_argv(argv)
            else:
                terminal_sequence([argv], "hyperlab: " + action_id)
            self.events.insert(0, SessionEvent(action_id, str(domain.get("name"))))
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))

    def _managed_action(self, action_id: str, domain: dict[str, Any], spec_row: dict[str, Any]) -> None:
        try:
            argv = resolve(action_id, spec=spec_row.get("path"))
            self.close_surface()
            terminal_sequence([argv], "hyperlab: %s %s" % (action_id, domain.get("name")))
            self.events.insert(0, SessionEvent(action_id, str(domain.get("name"))))
        except (ControlError, OSError) as exc:
            self.show_error(str(exc))

    def _destructive_managed(self, action_id: str, label: str, domain: dict[str, Any], spec_row: dict[str, Any]) -> None:
        name = str(domain.get("name"))
        self.exact_confirm(name, label, lambda: self._managed_action(action_id, domain, spec_row))

    def _build_create(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        if not self.model.catalog:
            content.append(text_label("The catalog is unavailable.", "mock-why", "warning"))
            scroll.set_child(content)
            return scroll

        image = Gtk.DropDown.new_from_strings([str(entry.get("id", "")) for entry in self.model.catalog])
        lifecycle = Gtk.DropDown.new_from_strings([])
        device = Gtk.DropDown.new_from_strings([])
        network = Gtk.DropDown.new_from_strings([])
        resource = Gtk.DropDown.new_from_strings(["minimum", "balanced", "performance"])
        for hidden in (image, lifecycle, device, network, resource):
            hidden.set_visible(False)
        name = Gtk.Entry(); name.set_placeholder_text("e.g. arch-dev-02")
        purpose = Gtk.Entry(); purpose.set_visible(False)
        keys = Gtk.DropDown.new_from_strings(self._ssh_key_paths())
        key_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        key_row.append(text_label("PUBLIC SSH KEY", "mock-kick", "field-label", wrap=False))
        key_row.append(keys)

        steps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        steps.add_css_class("steps")
        step_values: list[Gtk.Label] = []
        step_boxes: list[Gtk.Box] = []
        for number, label in (("01", "Image"), ("02", "Lifecycle"), ("03", "Device"), ("04", "Segment"), ("05", "Name")):
            item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            item.add_css_class("step"); item.set_hexpand(True)
            item.append(text_label(number, "step-number", wrap=False))
            item.append(text_label(label, "step-label", wrap=False))
            value = text_label("—", "step-value", wrap=False)
            item.append(value); step_values.append(value); step_boxes.append(item); steps.append(item)
        content.append(steps)

        image_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        image_grid.set_column_homogeneous(True)
        image_grid.add_css_class("options-grid")
        image_buttons: dict[str, Gtk.Button] = {}
        for index, entry in enumerate(self.model.catalog):
            image_id = str(entry.get("id", ""))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            box.append(text_label(str(entry.get("display_name") or image_id), "option-title", wrap=False))
            detail = "%s · %s" % (" / ".join(entry.get("device_profiles") or []), " / ".join(entry.get("lifecycles") or []))
            box.append(text_label(detail, "option-detail"))
            if not entry.get("ready"):
                box.append(text_label(str(entry.get("blocked_reason") or "not ready"), "mock-why", "warning"))
            item = Gtk.Button(child=box); item.add_css_class("option-card")
            ready = bool(entry.get("ready"))
            item.set_sensitive(ready)
            if not ready:
                item.set_tooltip_text(str(entry.get("blocked_reason") or "Image is not ready"))
            item.connect("clicked", lambda _button, value=image_id: self._choose_create_value("image", value))
            image_buttons[image_id] = item
            image_grid.attach(item, index % 3, index // 3, 1, 1)
        preset_grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        preset_grid.set_column_homogeneous(True)
        preset_grid.add_css_class("options-grid")
        preset_buttons: dict[str, Gtk.Button] = {}
        catalog_ids = {str(entry.get("id") or "") for entry in self.model.catalog}
        for index, (preset_id, preset) in enumerate(CREATE_PRESETS.items()):
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            body.append(text_label(str(preset["title"]), "option-title", wrap=False))
            preset_entry = next(
                (
                    entry
                    for entry in self.model.catalog
                    if str(entry.get("id") or "") == str(preset["image"])
                ),
                None,
            )
            detail = str(preset["detail"])
            if isinstance(preset_entry, dict):
                profiles = preset_entry.get("resource_profiles") or {}
                resources = profiles.get(str(preset["resource"])) or {}
                memory = resources.get("memory_mb")
                memory_text = (
                    "%g GiB" % (int(memory) / 1024)
                    if isinstance(memory, int) and memory
                    else str(memory or "auto")
                )
                detail += " · %s / %s vCPU / %s GiB" % (
                    memory_text,
                    resources.get("vcpus") or "—",
                    resources.get("disk_gib") or "—",
                )
            body.append(text_label(detail, "option-detail"))
            item = Gtk.Button(child=body)
            item.add_css_class("option-card")
            available = str(preset["image"]) in catalog_ids
            item.set_sensitive(available)
            if not available:
                item.set_tooltip_text("Required golden image is not present in the catalog")
            item.connect(
                "clicked",
                lambda _button, value=preset_id: self._apply_create_preset(value),
            )
            preset_buttons[preset_id] = item
            preset_grid.attach(item, index % 3, index // 3, 1, 1)

        content.append(text_label("QUICK PRESETS", "mock-kick", wrap=False))
        content.append(preset_grid)
        content.append(text_label("GOLDEN IMAGE — FROM images/ MANIFESTS", "mock-kick", wrap=False))
        content.append(image_grid)

        lifecycle_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        network_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        resource_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for title, box in (("LIFECYCLE", lifecycle_box), ("DEVICE PROFILE", device_box), ("SEGMENT", network_box), ("RESOURCE PROFILE", resource_box)):
            content.append(text_label(title, "mock-kick", wrap=False)); content.append(box)

        content.append(text_label("NAME", "mock-kick", "field-label", wrap=False)); content.append(name)
        content.append(key_row)

        preview = text_label("Select the first image to build the spec preview.", "preview-spec")
        warning = text_label("", "mock-why", "warning"); warning.set_visible(False)
        content.append(text_label("SPEC PREVIEW", "mock-kick", wrap=False)); content.append(preview); content.append(warning)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dry = self._mock_pill("Preview / dry-run", lambda _button: self._preview_create())
        create = self._mock_pill("Write spec and create", lambda _button: self._commit_create(), style="primary")
        actions.append(dry); actions.append(create); content.append(actions)

        self.create_widgets = {
            "image": image, "lifecycle": lifecycle, "device": device, "network": network,
            "resource": resource, "name": name, "purpose": purpose, "keys": keys,
            "key_row": key_row, "review": preview, "warning": warning, "create": create,
            "step-values": step_values, "step-boxes": step_boxes,
            "image-buttons": image_buttons,
            "preset-buttons": preset_buttons,
            "choice-boxes": {"lifecycle": lifecycle_box, "device": device_box, "network": network_box, "resource": resource_box},
            "choice-buttons": {},
        }
        image.connect("notify::selected", lambda *_args: self._create_image_changed())
        lifecycle.connect("notify::selected", lambda *_args: self._create_review())
        device.connect("notify::selected", lambda *_args: self._create_device_changed())
        network.connect("notify::selected", lambda *_args: self._create_review())
        resource.connect("notify::selected", lambda *_args: self._create_review())
        name.connect("changed", lambda *_args: self._create_review())
        keys.connect("notify::selected", lambda *_args: self._create_review())
        self._create_image_changed()
        scroll.set_child(content)
        self._populate_create_inspector()
        return scroll

    def _dropdown_values(self, widget: Gtk.DropDown) -> list[str]:
        model = widget.get_model()
        if model is None:
            return []
        # The display-free shell harness models StringList as a plain list;
        # real GTK exposes the GListModel methods below. Supporting both keeps
        # the structural gate useful without weakening runtime behavior.
        if isinstance(model, (list, tuple)):
            return [str(item) for item in model]
        values = []
        for index in range(model.get_n_items()):
            item = model.get_item(index)
            if item is not None:
                values.append(item.get_string())
        return values

    def _choose_create_value(self, key: str, value: str) -> None:
        widget = self.create_widgets.get(key)
        if not isinstance(widget, Gtk.DropDown):
            return
        values = self._dropdown_values(widget)
        if value not in values:
            return
        widget.set_selected(values.index(value))
        if key == "image":
            if not self.create_widgets["name"].get_text().strip():
                self.create_widgets["name"].set_text("%s-%02d" % (value, len(self.model.domains) + 1))
            self._create_image_changed()
        elif key == "device":
            self._create_device_changed()
        else:
            self._create_review()

    def _apply_create_preset(self, preset_id: str) -> None:
        preset = CREATE_PRESETS.get(preset_id)
        if preset is None or not self.create_widgets:
            return
        image_id = str(preset["image"])
        image_values = self._dropdown_values(self.create_widgets["image"])
        if image_id not in image_values:
            self.show_error("The preset image is not available in the current catalog.")
            return
        self.create_widgets["image"].set_selected(image_values.index(image_id))
        self._create_image_changed()
        for key in ("lifecycle", "device", "network", "resource"):
            self._choose_create_value(key, str(preset[key]))
        self.create_widgets["name"].set_text(
            "arch-minimal-%02d" % (len(self.model.domains) + 1)
        )
        self.create_widgets["purpose"].set_text(str(preset["purpose"]))
        self._create_review()

    def _sync_create_preset_state(self) -> None:
        if not self.create_widgets:
            return
        current = {
            "image": dropdown_value(self.create_widgets["image"]),
            "lifecycle": dropdown_value(self.create_widgets["lifecycle"]),
            "device": dropdown_value(self.create_widgets["device"]),
            "network": dropdown_value(self.create_widgets["network"]),
            "resource": dropdown_value(self.create_widgets["resource"]),
        }
        for preset_id, item in self.create_widgets.get("preset-buttons", {}).items():
            preset = CREATE_PRESETS[preset_id]
            matches = all(
                str(current[key] or "") == str(preset[key])
                for key in current
            )
            if matches:
                item.add_css_class("selected")
            else:
                item.remove_css_class("selected")

    def _render_network_choice_box(self, allowed: list[str]) -> None:
        box = self.create_widgets["choice-boxes"]["network"]
        clear_box(box)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_column_homogeneous(True)
        grid.add_css_class("options-grid")
        buttons: dict[str, Gtk.Button] = {}
        current = dropdown_value(self.create_widgets["network"])
        order = ("clean", "dev", "services", "dirty", "lab")
        for index, value in enumerate(order):
            meta = DOMAIN_META[value]
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            body.append(text_label(value, "option-title", wrap=False))
            body.append(text_label(meta["subtitle"], "option-detail"))
            item = Gtk.Button(child=body)
            item.add_css_class("option-card")
            item.add_css_class("domain-%s" % value)
            permitted = value in allowed
            item.set_sensitive(permitted)
            if permitted:
                item.connect(
                    "clicked",
                    lambda _button, v=value: self._choose_create_value("network", v),
                )
            else:
                item.set_tooltip_text(
                    "This image/device combination does not permit the %s segment" % value
                )
            if value == current:
                item.add_css_class("selected")
            buttons[value] = item
            grid.attach(item, index % 3, index // 3, 1, 1)
        box.append(grid)
        self.create_widgets["choice-buttons"]["network"] = buttons

    def _render_create_choice_box(self, key: str, values: list[str], blurbs: dict[str, str]) -> None:
        box = self.create_widgets["choice-boxes"][key]
        clear_box(box)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8); grid.set_column_homogeneous(True); grid.add_css_class("options-grid")
        buttons: dict[str, Gtk.Button] = {}
        current = dropdown_value(self.create_widgets[key])
        for index, value in enumerate(values):
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            body.append(text_label(value, "option-title", wrap=False))
            if value in blurbs:
                body.append(text_label(blurbs[value], "option-detail"))
            item = Gtk.Button(child=body); item.add_css_class("option-card")
            if value == current: item.add_css_class("selected")
            item.connect("clicked", lambda _button, k=key, v=value: self._choose_create_value(k, v))
            buttons[value] = item
            grid.attach(item, index % 3, index // 3, 1, 1)
        box.append(grid)
        self.create_widgets["choice-buttons"][key] = buttons

    def _populate_create_inspector(self) -> None:
        inspect_holder = getattr(self, "inspect_holder", None)
        if inspect_holder is None:
            return
        clear_box(inspect_holder)
        inspect_holder.append(text_label("WHAT HAPPENS WHEN YOU CREATE", "mock-kick", wrap=False))
        for line in (
            "1 · compose write creates vm-specs/<name>.yml on the host",
            "2 · vm-create builds the libvirt domain from the golden image",
            "3 · the machine remains OFF until you start it from Machines",
            "4 · no cross-segment path exists unless an explicit link is opened",
        ):
            label = text_label(line, "mock-why"); label.set_margin_bottom(9); inspect_holder.append(label)
        network = dropdown_value(self.create_widgets.get("network")) if self.create_widgets else None
        if network in DOMAIN_META:
            rank = {"clean": 0, "dev": 0, "services": 1, "dirty": 2, "lab": 3}[network]
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0); group.add_css_class("mock-group")
            group.append(text_label("INHERITED TRUST", "mock-kick", "mock-group-title", wrap=False))
            self._append_kv(group, "domain", network)
            self._append_kv(group, "GPU rank", str(rank))
            self._append_kv(group, "DHCP", "libvirt" if network != "lab" else "none")
            inspect_holder.append(group)

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
        self._render_create_choice_box("lifecycle", self._dropdown_values(self.create_widgets["lifecycle"]), {
            "permanent": "keeps its disk between boots",
            "disposable": "explicitly resettable from the golden image",
        })
        self._render_create_choice_box("device", self._dropdown_values(self.create_widgets["device"]), {
            "standard": "virtio devices only",
            "vfio": "takes the GPU and enters the trust ladder",
        })
        self._render_create_choice_box("resource", self._dropdown_values(self.create_widgets["resource"]), {
            "minimum": "smallest reviewed profile",
            "balanced": "default workstation profile",
            "performance": "maximum reviewed profile",
        })
        for image_id, item in self.create_widgets["image-buttons"].items():
            if image_id == str(entry.get("id")): item.add_css_class("selected")
            else: item.remove_css_class("selected")
        self._create_device_changed()

    def _create_device_changed(self) -> None:
        entry = self._selected_image()
        device = dropdown_value(self.create_widgets["device"])
        if entry is None or device is None:
            return
        mapping = entry.get("network_profiles_by_device") or {}
        defaults = entry.get("defaults") or {}
        allowed_networks = list(mapping.get(device) or [])
        self._set_dropdown(
            self.create_widgets["network"],
            allowed_networks,
            defaults.get("network_profile"),
        )
        self._render_network_choice_box(allowed_networks)
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
            warning.set_text("Blocked image: %s" % (entry.get("blocked_reason") or "not ready")); warning.set_visible(True)
        elif entry.get("cloud_init") and not key_path:
            warning.set_text("This image requires a valid ~/.ssh/*.pub key."); warning.set_visible(True)
        else:
            warning.set_visible(False)
        mode = str((entry.get("defaults") or {}).get("looking_glass_mode") or "")
        if device == "vfio" and entry.get("os_family") == "windows":
            transport = "Looking Glass + SPICE recovery"
        elif device == "vfio" and mode == "linux-experimental":
            transport = "Looking Glass Linux experimental + SPICE recovery"
        elif device == "vfio":
            transport = "GPU / SPICE recovery"
        else:
            transport = "SPICE / virt-viewer"
        self.create_widgets["review"].set_text(
            "schema_version: 1\n"
            "name: %s\n"
            "image: %s\n"
            "lifecycle: %s\n"
            "device_profile: %s\n"
            "network_profile: %s\n"
            "resource_profile: %s\n"
            "owner: %s\n"
            "display: %s"
            % (
                name or "—",
                entry.get("id") or "—",
                lifecycle or "—",
                device or "—",
                network or "—",
                resource or "—",
                getpass.getuser(),
                transport,
            )
        )
        values = [str(entry.get("id") or "—"), lifecycle or "—", device or "—", network or "—", name or "—"]
        first_missing = next((i for i, value in enumerate(values) if value == "—"), -1)
        for index, (box, label) in enumerate(zip(self.create_widgets["step-boxes"], self.create_widgets["step-values"])):
            label.set_text(values[index]); box.remove_css_class("done"); box.remove_css_class("now")
            if values[index] != "—": box.add_css_class("done")
            elif index == first_missing: box.add_css_class("now")
        for key in ("lifecycle", "device", "network", "resource"):
            current = dropdown_value(self.create_widgets[key])
            for value, item in self.create_widgets["choice-buttons"].get(key, {}).items():
                if value == current: item.add_css_class("selected")
                else: item.remove_css_class("selected")
        self._sync_create_preset_state()
        self._populate_create_inspector()

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
                self.select_section("vms")
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
        inspect_holder = getattr(self, "inspect_holder", None)
        if inspect_holder is not None:
            clear_box(inspect_holder)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        canvas = Gtk.Fixed(); canvas.add_css_class("network-canvas"); canvas.set_size_request(760, 470)
        positions = {
            "clean": (24, 18), "services": (24, 132), "lab": (24, 246),
            "dev": (376, 18), "dirty": (376, 132),
        }
        subnets = {"clean": "10.10.1.0/24", "dirty": "10.10.2.0/24", "dev": "10.10.3.0/24", "lab": "10.10.4.0/24", "services": "10.10.5.0/24"}
        for domain_id in ("clean", "services", "lab", "dev", "dirty"):
            zone = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            zone.add_css_class("network-zone"); zone.add_css_class("domain-%s" % domain_id); zone.set_size_request(336, 96)
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            dot = Gtk.Box(); dot.add_css_class("domain-dot-%s" % domain_id); head.append(dot)
            head.append(text_label(DOMAIN_META[domain_id]["title"], "mock-section-title", wrap=False))
            head.append(text_label(subnets[domain_id], "mock-section-net", wrap=False)); zone.append(head)
            attached = [vm for vm in self.model.domains if self._domain_for_vm(vm) == domain_id]
            node_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            node_body.append(text_label(domain_id, "network-node-title", wrap=False))
            node_body.append(text_label("%d machines · %s" % (len(attached), "DHCP off" if domain_id == "lab" else "DHCP libvirt"), "network-node-sub", wrap=False))
            node = Gtk.Button(child=node_body); node.add_css_class("network-node"); node.add_css_class("domain-%s" % domain_id)
            if getattr(self, "selected_network", "dev") == domain_id:
                node.add_css_class("selected")
            node.connect("clicked", lambda _button, value=domain_id: self._select_network(value))
            zone.append(node)
            x, y = positions[domain_id]; canvas.put(zone, x, y)
        content.append(canvas)
        content.append(text_label("Select a segment. Links are explicit; no path exists unless the repository declares one.", "mock-why"))
        dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); dock.add_css_class("network-dock")
        self._populate_network_dock(dock, getattr(self, "selected_network", "dev"))
        content.append(dock)
        scroll.set_child(content)
        return scroll

    def _select_network(self, domain_id: str) -> None:
        if domain_id in DOMAIN_META:
            self.selected_network = domain_id
            self.rebuild_current()

    def _populate_network_dock(self, dock: Gtk.Box, domain_id: str) -> None:
        clear_box(dock)
        domain_id = domain_id if domain_id in DOMAIN_META else "dev"
        dock.append(text_label("SEGMENT", "mock-kick", wrap=False))
        dock.append(text_label(DOMAIN_META[domain_id]["title"], "inspect-title", wrap=False))
        attached = [vm for vm in self.model.domains if self._domain_for_vm(vm) == domain_id]
        rank = {"clean": 0, "dev": 0, "services": 1, "dirty": 2, "lab": 3}[domain_id]
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._append_kv(details, "domain", domain_id)
        self._append_kv(details, "GPU rank", str(rank))
        self._append_kv(details, "DHCP", "none" if domain_id == "lab" else "libvirt")
        self._append_kv(details, "machines", str(len(attached)))
        dock.append(details)
        dock.append(text_label("Network create, links and NIC writes remain absent until hyperlabctl exposes reviewed write actions.", "mock-why"))

    def _build_gpu(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        gpu_state = self.model.status.get("gpu") if isinstance(self.model.status, dict) else None
        owner = ""
        if isinstance(gpu_state, dict):
            owner = str(gpu_state.get("owner") or gpu_state.get("domain") or "")
        owner_vm = next((vm for vm in self.model.domains if str(vm.get("name")) == owner), None)
        current_domain = self._domain_for_vm(owner_vm) if owner_vm else ""
        ladder = ((0, ("clean", "dev")), (1, ("services",)), (2, ("dirty",)), (3, ("lab",)))
        for level, domains in ladder:
            rung = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12); rung.add_css_class("gpu-rung")
            if current_domain in domains: rung.add_css_class("current")
            number = text_label(str(level), "rung-number", wrap=False); number.set_xalign(.5); rung.append(number)
            chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6); chips.set_hexpand(True)
            for domain_id in domains:
                chip = text_label(DOMAIN_META[domain_id]["title"], "domain-chip", "domain-chip-%s" % domain_id, wrap=False); chips.append(chip)
            rung.append(chips)
            if current_domain in domains and owner:
                rung.append(text_label(owner, "rung-hold", wrap=False))
            content.append(rung)
        content.append(text_label("The ladder applies only to GPU handoff. Network trust remains an explicit graph.", "mock-why"))
        scroll.set_child(content)
        inspect_holder = getattr(self, "inspect_holder", None)
        if inspect_holder is not None:
            clear_box(inspect_holder)
            inspect_holder.append(text_label("GPU TRANSACTION", "mock-kick", wrap=False))
            inspect_holder.append(text_label(owner or "Host", "inspect-title", wrap=False))
            inspect_holder.append(text_label("runtime owner", "inspect-subtitle"))
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self._append_kv(info, "owner", owner or "host")
            self._append_kv(info, "Linux VFIO", "Looking Glass experimental + SPICE recovery")
            self._append_kv(info, "Windows VFIO", "Looking Glass + SPICE recovery")
            self._append_kv(info, "standard", "SPICE / virt-viewer")
            inspect_holder.append(info)
        return scroll


    def _nitro_write(self, args: list[str], event_title: str) -> None:
        try:
            result = run_nitro_json(*args)
        except ControlError as exc:
            self.events.insert(0, SessionEvent(event_title, str(exc), "error"))
            self.show_error(str(exc))
            return
        self.events.insert(
            0,
            SessionEvent(event_title, json.dumps(result, sort_keys=True)),
        )
        self.rebuild_current()



    def _flush_pending_theme_sway_reload(self) -> None:
        if not self._theme_sway_reload_pending:
            return

        self._theme_sway_reload_pending = False
        # Do not wait here. A Sway reload executes the resident-session
        # supervisor, which is allowed to replace this process only after the
        # surface has already been hidden by close_surface().
        try:
            subprocess.Popen(
                ["/usr/bin/swaymsg", "-q", "reload"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self.events.insert(
                0,
                SessionEvent(
                    "HyperLab theme",
                    "deferred Sway reload failed: %s" % exc,
                    "error",
                ),
            )

    def _nitro_set_theme(self, theme: str) -> None:
        if theme not in DESKTOP_THEMES:
            self.show_error("Unknown HyperLab desktop theme.")
            return
        try:
            run_theme("set", theme)
        except ControlError as exc:
            self.events.insert(0, SessionEvent("HyperLab theme", str(exc), "error"))
            self.show_error(str(exc))
            return

        # The helper owns palette and wallpaper state. The resident application
        # reloads every cached surface after the transaction; re-entering the
        # same GApplication from inside the helper is deliberately suppressed.
        application = self.get_application()
        reload_all = getattr(application, "reload_theme", None)
        if callable(reload_all):
            reload_all()
        else:
            self.reload_theme()
        self._theme_sway_reload_pending = True
        status = self.nitro_widgets.get("theme_status")
        if isinstance(status, Gtk.Label):
            status.set_text("Current theme: %s" % theme.upper())
        for name in DESKTOP_THEMES:
            item = self.nitro_widgets.get("theme_%s" % name)
            if isinstance(item, Gtk.Button):
                if name == theme:
                    item.add_css_class("active")
                else:
                    item.remove_css_class("active")
        self.events.insert(0, SessionEvent("HyperLab theme", theme))

    def _nitro_theme_card(self) -> Gtk.Box:
        item = card()
        item.append(text_label("Desktop theme", "section-title", wrap=False))
        item.append(text_label(
            "Appearance only. Trust colors keep their fixed semantic meaning.",
            "caption",
        ))

        try:
            current = run_theme("status").strip().lower()
            if current not in DESKTOP_THEMES:
                raise ControlError("theme helper returned an unknown theme")
            available = True
        except ControlError as exc:
            current = ""
            available = False
            item.append(text_label(str(exc), "status-blocked"))

        current_label = text_label(
            "Current theme: %s" % (current.upper() if current else "UNAVAILABLE"),
            "card-title",
            wrap=False,
        )
        item.append(current_label)
        self.nitro_widgets["theme_status"] = current_label

        choices = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for theme in DESKTOP_THEMES:
            choice = Gtk.Button(label=theme.title())
            choice.set_hexpand(True)
            choice.set_sensitive(available)
            if theme == current:
                choice.add_css_class("active")
            choice.connect(
                "clicked",
                lambda _button, name=theme: self._nitro_set_theme(name),
            )
            choices.append(choice)
            self.nitro_widgets["theme_%s" % theme] = choice
        item.append(choices)
        return item

    def _nitro_apply_fans(self) -> None:
        cpu = self.nitro_widgets.get("fan_cpu")
        gpu = self.nitro_widgets.get("fan_gpu")
        if not isinstance(cpu, Gtk.SpinButton) or not isinstance(gpu, Gtk.SpinButton):
            self.show_error("Nitro fan controls are unavailable.")
            return
        self._nitro_write(
            ["fan", str(cpu.get_value_as_int()), str(gpu.get_value_as_int())],
            "Nitro fan policy",
        )

    def _nitro_apply_battery(self) -> None:
        limiter = self.nitro_widgets.get("battery_limiter")
        if not isinstance(limiter, Gtk.Switch):
            self.show_error("Nitro battery control is unavailable.")
            return
        self._nitro_write(
            ["battery", "on" if limiter.get_active() else "off"],
            "Nitro battery limiter",
        )

    def _nitro_apply_rgb(self) -> None:
        zones: list[str] = []
        for index in range(1, 5):
            widget = self.nitro_widgets.get("zone%d" % index)
            if not isinstance(widget, Gtk.Entry):
                self.show_error("Nitro RGB controls are unavailable.")
                return
            value = widget.get_text().strip().lower()
            if re.fullmatch(r"[0-9a-f]{6}", value) is None:
                self.show_error(
                    "Zone %d must contain exactly six hexadecimal digits." % index
                )
                return
            zones.append(value)

        brightness = self.nitro_widgets.get("brightness")
        if not isinstance(brightness, Gtk.SpinButton):
            self.show_error("Nitro brightness control is unavailable.")
            return

        self._nitro_write(
            ["rgb", str(brightness.get_value_as_int()), *zones],
            "Nitro four-zone RGB",
        )

    def _build_nitro(self) -> Gtk.Widget:
        scroll, content = self._page(
            "Nitro Control Board",
            "Laptop hardware and desktop appearance in one normal-user control surface.",
        )
        self.nitro_widgets = {}
        content.append(self._nitro_theme_card())

        try:
            status = run_nitro_json("status")
        except ControlError as exc:
            offline = card()
            offline.append(text_label("Runtime backend unavailable", "status-blocked", wrap=False))
            offline.append(text_label(str(exc), "caption"))
            offline.append(button("Retry", lambda _button: self.rebuild_current()))
            content.append(offline)
            return scroll

        capabilities = status.get("capabilities")
        runtime = status.get("runtime")
        capabilities = capabilities if isinstance(capabilities, dict) else {}
        runtime = runtime if isinstance(runtime, dict) else {}

        summary = card()
        summary.append(text_label(str(status.get("model") or "Acer Nitro"), "card-title", wrap=False))
        summary.append(text_label("Runtime backend online", "status-ready", wrap=False))
        summary.append(text_label(
            "Changes are runtime-only; Ansible still owns boot policy.",
            "caption",
        ))
        content.append(summary)

        if capabilities.get("fan") is True:
            fan = str(runtime.get("fan") or "")
            fan_parts = fan.split(",")
            fan_valid = (
                len(fan_parts) == 2
                and all(part.isdigit() and 0 <= int(part) <= 100 for part in fan_parts)
            )

            cooling = card()
            cooling.append(text_label("Cooling", "section-title", wrap=False))
            cooling.append(text_label(
                "Explicit CPU/GPU percentages from the validated Nitro ABI.",
                "caption",
            ))

            fan_grid = self._grid(2)
            for index, label in enumerate(("CPU fan", "GPU fan")):
                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                cell.append(text_label(label, "card-title", wrap=False))
                spin = Gtk.SpinButton.new_with_range(0, 100, 1)
                if fan_valid:
                    spin.set_value(int(fan_parts[index]))
                spin.set_sensitive(fan_valid)
                cell.append(spin)
                self.nitro_widgets["fan_cpu" if index == 0 else "fan_gpu"] = spin
                self._grid_add(fan_grid, cell, index)
            cooling.append(fan_grid)

            fan_apply = button(
                "Apply fan values",
                lambda _button: self._nitro_apply_fans(),
                "suggested-action",
            )
            fan_apply.set_sensitive(fan_valid)
            cooling.append(fan_apply)
            if not fan_valid:
                cooling.append(text_label(
                    "Fan readback is malformed; writes are disabled.",
                    "status-blocked",
                ))
            content.append(cooling)

        if capabilities.get("battery_limiter") is True:
            battery = card()
            battery.append(text_label("Battery", "section-title", wrap=False))
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            label = text_label("Battery charge limiter", "card-title", wrap=False)
            label.set_hexpand(True)
            row.append(label)
            limiter = Gtk.Switch()
            limiter.set_active(runtime.get("battery_limiter") is True)
            row.append(limiter)
            battery.append(row)
            battery.append(text_label(
                "Apply changes live; reboot policy remains managed by Ansible.",
                "caption",
            ))
            battery.append(button(
                "Apply battery limiter",
                lambda _button: self._nitro_apply_battery(),
            ))
            self.nitro_widgets["battery_limiter"] = limiter
            content.append(battery)

        if capabilities.get("per_zone") is True:
            value = str(runtime.get("per_zone") or "")
            parts = value.split(",")
            rgb_valid = (
                len(parts) == 5
                and all(re.fullmatch(r"[0-9a-fA-F]{6}", part) for part in parts[:4])
                and parts[4].isdigit()
                and 0 <= int(parts[4]) <= 100
            )

            keyboard = card()
            keyboard.append(text_label("Keyboard", "section-title", wrap=False))
            keyboard.append(text_label(
                "Four-zone static color and brightness use only the physically validated path.",
                "caption",
            ))

            zones = self._grid(4)
            for index in range(4):
                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                cell.append(text_label("Zone %d" % (index + 1), "card-title", wrap=False))
                entry = Gtk.Entry()
                entry.set_placeholder_text("RRGGBB")
                entry.set_text(parts[index].lower() if rgb_valid else "")
                entry.set_sensitive(rgb_valid)
                cell.append(entry)
                self.nitro_widgets["zone%d" % (index + 1)] = entry
                self._grid_add(zones, cell, index)
            keyboard.append(zones)

            brightness_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            brightness_label = text_label("Brightness", "card-title", wrap=False)
            brightness_label.set_hexpand(True)
            brightness_row.append(brightness_label)
            brightness = Gtk.SpinButton.new_with_range(0, 100, 1)
            if rgb_valid:
                brightness.set_value(int(parts[4]))
            brightness.set_sensitive(rgb_valid)
            brightness_row.append(brightness)
            keyboard.append(brightness_row)
            self.nitro_widgets["brightness"] = brightness

            rgb_apply = button(
                "Apply four-zone RGB",
                lambda _button: self._nitro_apply_rgb(),
                "suggested-action",
            )
            rgb_apply.set_sensitive(rgb_valid)
            keyboard.append(rgb_apply)
            if not rgb_valid:
                keyboard.append(text_label(
                    "RGB readback is malformed; writes are disabled.",
                    "status-blocked",
                ))
            content.append(keyboard)

        if not any(
            capabilities.get(name) is True
            for name in ("fan", "battery_limiter", "per_zone")
        ):
            content.append(text_label(
                "The backend advertises no interactive Nitro controls.",
                "warning",
            ))

        inspect_holder = getattr(self, "inspect_holder", None)
        if inspect_holder is not None:
            clear_box(inspect_holder)
            inspect_holder.append(text_label("NITRO CONTROL BOARD", "mock-kick", wrap=False))
            inspect_holder.append(text_label(
                str(status.get("model") or "Acer Nitro"),
                "inspect-title",
                wrap=False,
            ))
            inspect_holder.append(text_label(
                "normal-user control boundary",
                "inspect-subtitle",
            ))
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self._append_kv(details, "backend", "online")
            self._append_kv(
                details,
                "persistence",
                str(status.get("persistence") or "unknown"),
            )
            self._append_kv(
                details,
                "fan",
                "available" if capabilities.get("fan") is True else "hidden",
            )
            self._append_kv(
                details,
                "battery",
                "available" if capabilities.get("battery_limiter") is True else "hidden",
            )
            self._append_kv(
                details,
                "four-zone RGB",
                "available" if capabilities.get("per_zone") is True else "hidden",
            )
            inspect_holder.append(details)
            inspect_holder.append(text_label(
                "Only capabilities advertised by the broker become controls.",
                "mock-why",
            ))

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

    def close_visible_surfaces(self) -> None:
        for window in self.windows.values():
            if window.get_visible():
                window.close_surface()
        self.surface_hidden()

    def surface_hidden(self) -> bool:
        return False

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
