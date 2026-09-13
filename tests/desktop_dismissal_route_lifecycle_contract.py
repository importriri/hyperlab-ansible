#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


source = MANAGER.read_text(encoding="utf-8")
tree = ast.parse(source)
classes = {
    node.name: node
    for node in tree.body
    if isinstance(node, ast.ClassDef)
}
window_class = classes.get("HyperlabWindow")
app_class = classes.get("HyperlabApplication")
require(window_class is not None, "HyperlabWindow class missing")
require(app_class is not None, "HyperlabApplication class missing")


def method_node(class_node, name):
    matches = [
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    require(len(matches) == 1, f"{class_node.name}.{name} must exist exactly once")
    return matches[0]


window_methods = [
    method_node(window_class, name)
    for name in (
        "_on_destroyed",
        "_invalidate_pending_dismissal",
        "_prepare_show",
        "_defer_input_dismissal",
        "_finish_input_dismissal",
        "close_surface",
    )
]
app_methods = [
    method_node(app_class, name)
    for name in (
        "_ensure_window",
        "close_visible_surfaces",
        "keep_warm",
        "route",
        "_surface_destroyed",
    )
]


class FakeGLib:
    SOURCE_REMOVE = False
    next_id = 1
    callbacks = {}
    removed = []
    timeouts = []

    @classmethod
    def reset(cls):
        cls.next_id = 1
        cls.callbacks = {}
        cls.removed = []
        cls.timeouts = []

    @classmethod
    def idle_add(cls, callback, *args):
        source_id = cls.next_id
        cls.next_id += 1
        cls.callbacks[source_id] = (callback, args)
        return source_id

    @classmethod
    def source_remove(cls, source_id):
        cls.removed.append(source_id)
        return True

    @classmethod
    def timeout_add(cls, delay, callback, *args):
        source_id = cls.next_id
        cls.next_id += 1
        cls.timeouts.append((source_id, delay, callback, args))
        return source_id

    @classmethod
    def fire_even_if_removed(cls, source_id):
        callback, args = cls.callbacks[source_id]
        return callback(*args)


window_support = ast.parse(
    """
def __init__(self, app, surface_mode, initial_section):
    self._app = app
    self.surface_mode = surface_mode
    self.current_section = initial_section
    self.last_refresh_monotonic = time.monotonic()
    self._dismiss_source_id = 0
    self._visibility_generation = 0
    self._destroyed = False
    self._visible = False
    self._callbacks = {}
    self.keyboard_capture = False
    self.present_count = 0
    self.reload_count = 0
    self.refresh_count = 0
    self.connect("destroy", self._on_destroyed)

def connect(self, signal, callback):
    self._callbacks.setdefault(signal, []).append(callback)
    return len(self._callbacks[signal])

def destroy(self):
    if self._destroyed:
        return
    callbacks = list(self._callbacks.get("destroy", []))
    for callback in callbacks:
        callback(self)

def set_visible(self, value):
    self._visible = bool(value)

def get_visible(self):
    return self._visible

def _set_keyboard_capture(self, enabled):
    self.keyboard_capture = bool(enabled)

def _flush_pending_theme_sway_reload(self):
    return None

def get_application(self):
    return self._app

def reload_theme(self):
    self.reload_count += 1

def select_section(self, section):
    self.current_section = section

def present(self):
    self.present_count += 1

def refresh(self):
    self.refresh_count += 1
"""
).body

app_support = ast.parse(
    """
def __init__(self):
    self.windows = {}
    self._held_warm = False
    self.hold_count = 0

def hold(self):
    self.hold_count += 1

def surface_hidden(self):
    return False

def _refresh_visible_windows(self):
    for window in list(self.windows.values()):
        if window.get_visible():
            window.refresh()
    return False
"""
).body

module = ast.Module(
    body=[
        ast.ImportFrom(
            module="__future__",
            names=[ast.alias(name="annotations")],
            level=0,
        ),
        ast.ClassDef(
            name="TestWindow",
            bases=[],
            keywords=[],
            body=window_support + window_methods,
            decorator_list=[],
        ),
        ast.ClassDef(
            name="TestApp",
            bases=[],
            keywords=[],
            body=app_support + app_methods,
            decorator_list=[],
        ),
    ],
    type_ignores=[],
)
ast.fix_missing_locations(module)

namespace = {
    "GLib": FakeGLib,
    "SECTIONS": {"vms", "status", "problems"},
    "time": time,
}
exec(compile(module, str(MANAGER), "exec"), namespace)
TestWindow = namespace["TestWindow"]
TestApp = namespace["TestApp"]
namespace["HyperlabWindow"] = TestWindow

FakeGLib.reset()
app = TestApp()

app.route("drawer", "vms", toggle=False)
drawer_a = app.windows["drawer"]
require(drawer_a.get_visible(), "drawer A was not made visible")
require(drawer_a.keyboard_capture, "drawer A did not request keyboard capture")
drawer_a._defer_input_dismissal()
drawer_a_source = drawer_a._dismiss_source_id
require(drawer_a_source > 0, "drawer A did not queue dismissal")

drawer_a.close_surface()
require(drawer_a._destroyed, "drawer A was not destroyed on close")
require("drawer" not in app.windows, "destroyed drawer remained cached")

app.route("drawer", "vms", toggle=False)
drawer_b = app.windows["drawer"]
require(drawer_b is not drawer_a, "drawer replacement reused destroyed object")
require(drawer_b.get_visible(), "drawer B was not visible")
require(drawer_b.keyboard_capture, "drawer B did not own keyboard capture")

FakeGLib.fire_even_if_removed(drawer_a_source)
require(drawer_b.get_visible(), "stale drawer A callback hid replacement drawer B")
require(app.windows.get("drawer") is drawer_b, "stale drawer A callback evicted drawer B")

app.route("overlay", "status", toggle=False)
overlay_a = app.windows["overlay"]
require(overlay_a.get_visible(), "overlay A was not made visible")
overlay_a._defer_input_dismissal()
overlay_source = overlay_a._dismiss_source_id
require(overlay_source > 0, "overlay did not queue dismissal")

overlay_a.close_surface()
require(not overlay_a._destroyed, "overlay was destroyed instead of cached")
require(app.windows.get("overlay") is overlay_a, "hidden overlay left cache")
require(not overlay_a.get_visible(), "overlay stayed visible after close")

app.route("overlay", "status", toggle=False)
overlay_b = app.windows["overlay"]
require(overlay_b is overlay_a, "cached overlay was replaced on reopen")
require(overlay_b.get_visible(), "cached overlay did not reopen")
require(overlay_b.keyboard_capture, "reopened overlay did not reacquire keyboard capture")

FakeGLib.fire_even_if_removed(overlay_source)
require(overlay_b.get_visible(), "stale hidden-overlay callback closed reopened overlay")
require(app.windows.get("overlay") is overlay_b, "stale callback evicted cached overlay")

app.route("drawer", "vms", toggle=False)
drawer_c = app.windows["drawer"]
app.route("overlay", "problems", toggle=False)
overlay_c = app.windows["overlay"]
app.route("drawer", "vms", toggle=False)
drawer_d = app.windows["drawer"]
require(drawer_d is not drawer_c, "drawer lifecycle did not create fresh surface")
require(overlay_c is app.windows["overlay"], "overlay cache changed unexpectedly")

app.close_visible_surfaces()
require(
    all(not window.get_visible() for window in app.windows.values()),
    "close_visible_surfaces left a cached surface visible",
)

print("HyperLab drawer/application route lifecycle contract: OK")
