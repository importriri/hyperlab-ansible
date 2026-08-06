#!/usr/bin/env python3
"""Build all nine sections rather than only the drawer.

A section that crashes on first click stays hidden until someone clicks it.
Each section is built with a fake model and any failure is recorded.
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gtkstub
gtkstub.install()

spec = importlib.util.spec_from_file_location(
    "manager", Path(__file__).resolve().parent.parent.parent / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py")
manager = importlib.util.module_from_spec(spec)
sys.modules["manager"] = manager
spec.loader.exec_module(manager)
from gi.repository import Gtk  # noqa: E402


class FakeModel:
    """Minimal but realistic shape containing what the manager actually reads."""
    domains = [
        {"name": "arch-dev-01", "domain": "dev", "state": "running", "vfio": False,
         "memory_mb": 4096, "network": "dev", "blocked": None, "spec": "arch-dev",
         "image": "arch", "lifecycle": "permanent", "device_profile": "standard"},
        {"name": "arch-lab-vfio", "domain": "lab", "state": "running", "vfio": True,
         "memory_mb": 16384, "network": "lab", "blocked": None, "spec": "arch-lab",
         "image": "arch", "lifecycle": "permanent", "device_profile": "vfio"},
        {"name": "parrot-lab", "domain": "lab", "state": "shut off", "vfio": False,
         "memory_mb": 0, "network": "lab",
         "blocked": {"short_mb": 512}, "spec": "parrot-disposable",
         "image": "parrot", "lifecycle": "disposable", "device_profile": "standard"},
    ]
    catalog = [
        {"name": "arch", "id": "arch", "sealed": True, "status": "sealed",
         "sha256": "f419d4e2", "virtual_size_gib": 2, "private": False},
        {"name": "debian", "id": "debian", "sealed": False, "status": "not-built",
         "sha256": None, "virtual_size_gib": 2, "private": False},
    ]
    specs = [
        {"name": "arch-dev", "image": "arch", "domain": "dev",
         "lifecycle": "permanent", "device_profile": "standard"},
        {"name": "parrot-disposable", "image": "parrot", "domain": "lab",
         "lifecycle": "disposable", "device_profile": "standard"},
    ]
    problems: list = []
    load_errors: list = []
    status: dict = {
        "host": {"profile": "nitro", "hostname": "nitro"},
        "trust": {"level": "medium-high", "percent": 85, "can_rise": True},
        "memory": {"total_mb": 16384, "available_mb": 7200, "reserved_mb": 2048},
        "gpu": {"model": "RTX 3060", "owner": None, "bound": False, "driver": "550.54"},
        "networks": [{"name": n, "state": "active"}
                     for n in ("clean", "dev", "lab", "dirty", "services")],
        "images": {"sealed": 1, "total": 6},
        "store": {"used_gib": 12, "total_gib": 400, "unsealed": 5},
        "domains": [],
    }

    @property
    def running_domains(self):
        return [d for d in self.domains if d["state"] == "running"]

    @property
    def ready_images(self):
        return [i for i in self.catalog if i["sealed"]]


def window(surface: str, section: str):
    win = object.__new__(manager.HyperlabWindow)
    win.model = FakeModel()
    win.surface = surface
    win.initial_section = section
    win.section = section
    win.drawer_tab = "apps"
    win.drawer_holder = None
    win.drawer_query = ""
    win.drawer_selected_domain = None
    win.selected_vm = None
    win.selected_domain = None
    win.query = ""
    win.create_widgets = {}
    win._grid_columns = {}
    win.section_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    win.buttons = {}
    win.toast = None
    win.events = []
    win.history = []
    win.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    return win


def main() -> int:
    passed, failed = [], []
    print("=== every section builds without crashing")
    for section in manager.SECTIONS:
        builder = getattr(manager.HyperlabWindow, "_build_%s" % section, None)
        if builder is None:
            failed.append((section, "missing _build_%s" % section))
            print("  FAIL %-13s missing builder" % section)
            continue
        win = window("overlay", section)
        try:
            result = builder(win)
            widgets = len(list(result.walk())) if hasattr(result, "walk") else 0
            passed.append(section)
            print("  ok   %-13s %3d widget" % (section, widgets))
        except Exception as exc:  # noqa: BLE001 - one failing section must not stop the sweep
            line = traceback.extract_tb(sys.exc_info()[2])[-1].lineno
            failed.append((section, "%s: %s (riga %s)" % (type(exc).__name__, exc, line)))
            print("  FAIL %-13s %s: %s  (riga %s)" % (section, type(exc).__name__, exc, line))

    print("\n=== every declared section has a builder")
    missing = [s for s in manager.SECTIONS
               if not hasattr(manager.HyperlabWindow, "_build_%s" % s)]
    print("  %s %d/%d" % ("ok  " if not missing else "FAIL",
                          len(manager.SECTIONS) - len(missing), len(manager.SECTIONS)))

    print("\n%s\npassed %d, failed %d" % ("=" * 58, len(passed), len(failed)))
    for section, why in failed:
        print("  FAIL %s -> %s" % (section, why))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
