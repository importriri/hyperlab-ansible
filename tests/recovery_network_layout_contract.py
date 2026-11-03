#!/usr/bin/env python3
"""Allocate real recovery Networks widgets with production CSS on a private display."""
from __future__ import annotations

import itertools
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

from recovery_gpu_ladder_contract import descendants, gtk_display, load_manager, run_gtk_worker


def run_without_xvfb() -> int:
    """Require the allocation check to work with only GTK's bundled server."""
    server = shutil.which("gtk4-broadwayd")
    assert server, "gtk4-broadwayd from GTK 4 is required for recovery layout allocation"
    with tempfile.TemporaryDirectory(prefix="hyperlab-gtk-bin-") as directory:
        (Path(directory) / "gtk4-broadwayd").symlink_to(server)
        with patch.dict(os.environ, {"PATH": directory, "DISPLAY": ":invalid",
                                     "WAYLAND_DISPLAY": "invalid"}):
            return run_gtk_worker(Path(__file__))


def main() -> int:
    with gtk_display() as gtk:
        from gi.repository import Gdk, GLib
        namespace = load_manager(gtk)
        window = namespace["HyperlabWindow"]()
        window.model = namespace["Model"]()
        window.inspect_holder = gtk.Box()
        css = gtk.CssProvider()
        css.load_from_data(namespace["CSS"].encode())
        gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for width, height, scale in ((760, 560, 1), (1000, 760, 1), (500, 560, 1), (760, 560, 2)):
            page = window._build_policies()
            zones = [item for item in descendants(page) if item.has_css_class("network-zone")]
            assert len(zones) == 5, "Networks lost a segment"
            if scale == 2:
                for zone in zones:
                    zone.append(gtk.Label(label="Additional segment detail\n" * 10))
            host = gtk.Window()
            host.set_default_size(width, height)
            host.set_child(page)
            host.present()
            until = time.monotonic() + 0.2
            while time.monotonic() < until:
                while GLib.MainContext.default().iteration(False):
                    pass
                time.sleep(0.005)
            parent = zones[0].get_parent()
            rects = []
            for zone in zones:
                ok, bounds = zone.compute_bounds(parent)
                assert ok and bounds.get_height() > 0, "segment was not allocated"
                rects.append((bounds.get_x(), bounds.get_y(), bounds.get_width(), bounds.get_height()))
            for left, right in itertools.combinations(rects, 2):
                ax, ay, aw, ah = left
                bx, by, bw, bh = right
                assert ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay, f"Networks tiles overlap at {width}x{height}: {left}, {right}"
            host.destroy()
    print("Recovery Networks layout contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() if "--gtk-worker" in sys.argv else run_without_xvfb())
