#!/usr/bin/env python3
"""Display-free structural validation of the compact resident drawer.

The Nitro contract is intentionally small: one scrollable content column, two
lightweight tabs, and an explicit escape hatch to the full Control Center.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gtkstub

gtkstub.install()
sys.path.insert(0, str(Path(__file__).parent.parent))

spec = importlib.util.spec_from_file_location(
    "manager",
    Path(__file__).resolve().parent.parent.parent
    / "roles/desktop/files/privatestack-hyperlab-domains.py",
)
manager = importlib.util.module_from_spec(spec)
sys.modules["manager"] = manager
spec.loader.exec_module(manager)

from gi.repository import Gtk  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "ok  " if condition else "FAIL"
    print(f"  {mark} {name}{'  — ' + detail if detail and not condition else ''}")


class FakeModel:
    domains = [
        {"name": "arch-dev-01", "network": "dev", "state": "running", "vfio": False},
        {"name": "arch-lab-vfio", "network": "lab", "state": "running", "vfio": True},
    ]
    catalog = [{"name": "arch", "sealed": True}]
    problems: list = []
    load_errors: list = []
    specs: list = []

    @property
    def running_domains(self):
        return [item for item in self.domains if item["state"] == "running"]

    @property
    def ready_images(self):
        return self.catalog


def build_drawer():
    window = object.__new__(manager.HyperlabWindow)
    window.model = FakeModel()
    window.surface_mode = "drawer"
    window.initial_section = "vms"
    window.current_section = "vms"
    window.drawer_tab = "apps"
    window.drawer_holder = None
    panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    window._build_drawer_shell(panel)
    return window, panel


def main() -> int:
    print("=== compact drawer structure")
    window, panel = build_drawer()

    contents = [widget for widget in panel.walk()
                if widget.has_css_class("drawer-content")]
    check("the single drawer content column exists", len(contents) == 1,
          f"found {len(contents)}")
    check("the old three-column sidebar is gone",
          not any(widget.has_css_class("drawer-sidebar") for widget in panel.walk()))
    check("the old right status rail is gone",
          not any(widget.has_css_class("drawer-status") for widget in panel.walk()))

    tabs = [widget.label for widget in panel.walk()
            if widget.has_css_class("nav-button") and widget.label]
    check("two compact tabs are present", tabs == ["VMs", "System"], f"{tabs}")

    labels = [widget.label for widget in panel.walk() if widget.label]
    check("the full manager is an explicit drawer action",
          "Full Control Center" in labels)
    check("the initial VM list is built without a second surface",
          "Virtual machines" in labels)

    window._select_drawer_tab("system")
    labels = [widget.label for widget in panel.walk() if widget.label]
    for expected in ("System summary", "Host Health", "GPU Passthrough", "Trust & Network"):
        check(f"system drawer shows {expected}", expected in labels)

    print(f"\n{'=' * 58}\npassed {len(PASSED)}, failed {len(FAILED)}")
    for name in FAILED:
        print(f"  FAIL {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
