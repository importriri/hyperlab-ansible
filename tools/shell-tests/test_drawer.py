#!/usr/bin/env python3
"""Display-free structural lock for the definitive compact machine drawer."""
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
    / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py",
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
        {
            "name": "arch-dev-01",
            "network": "dev",
            "state": "running",
            "vfio": False,
            "memory_mb": 4096,
            "vcpus": 4,
        },
        {
            "name": "arch-lab-vfio",
            "network": "lab",
            "state": "running",
            "vfio": True,
            "memory_mb": 8192,
            "vcpus": 6,
        },
    ]
    catalog = [{"name": "arch", "id": "arch", "sealed": True}]
    problems: list = []
    load_errors: list = []
    specs: list = []
    status: dict = {}

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
    window.header_status = None
    window.selected_vm = None
    window.create_widgets = {}
    window._grid_columns = {}
    panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    window._build_drawer_shell(panel)
    return window, panel


def main() -> int:
    print("=== definitive compact drawer structure")
    _window, panel = build_drawer()
    widgets = list(panel.walk())
    labels = [widget.label for widget in widgets if widget.label]

    check("the drawer title is exactly Machines", labels and labels[0] == "Machines", str(labels[:3]))
    check("the running badge mirrors the showcase", "2 running" in labels, str(labels[:4]))
    check("the legacy drawer tabs are absent",
          not any(widget.has_css_class("nav-button") or widget.has_css_class("drawer-tabs")
                  for widget in widgets))
    check("the legacy drawer search is absent",
          not any(widget.has_css_class("drawer-search") for widget in widgets))
    check("the legacy drawer footer is absent",
          not any(widget.has_css_class("drawer-footer") for widget in widgets))

    tiles = [widget for widget in widgets if widget.has_css_class("vm-tile")]
    check("the drawer renders the machine showcase", len(tiles) == 2, f"found {len(tiles)}")

    tile_grids = {tile.parent for tile in tiles if tile.parent is not None}
    two_columns = bool(tile_grids)
    for grid in tile_grids:
        cells = grid.props.get("cells", [])
        two_columns = two_columns and all(col in (0, 1) for col, _row, _w, _h in cells)
    check("machine tiles are locked to the two-column drawer showcase", two_columns)

    check("the New machine escape hatch remains visible", "＋  New machine" in labels)
    check("the old System drawer content is gone",
          all(label not in labels for label in (
              "System summary", "Host Health", "GPU Passthrough", "Trust & Network"
          )))

    print(f"\n{'=' * 58}\npassed {len(PASSED)}, failed {len(FAILED)}")
    for name in FAILED:
        print(f"  FAIL {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
