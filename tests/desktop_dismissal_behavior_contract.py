#!/usr/bin/env python3
"""Execute the real drawer deferred-dismissal lifecycle without a display."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"


class FakeGLib:
    SOURCE_REMOVE = False
    next_id = 1
    callbacks = {}
    removed = []

    @classmethod
    def reset(cls):
        cls.next_id = 1
        cls.callbacks = {}
        cls.removed = []

    @classmethod
    def idle_add(cls, callback, *args):
        source_id = cls.next_id
        cls.next_id += 1
        cls.callbacks[source_id] = (callback, args)
        return source_id

    @classmethod
    def source_remove(cls, source_id):
        cls.removed.append(source_id)
        return cls.callbacks.pop(source_id, None) is not None


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def subject_type():
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    window = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HyperlabWindow"
    )
    wanted = {
        "_on_destroyed",
        "_invalidate_pending_dismissal",
        "_prepare_show",
        "_defer_input_dismissal",
        "_finish_input_dismissal",
        "_defer_escape_dismissal",
        "close_surface",
    }
    methods = [
        node
        for node in window.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    require({node.name for node in methods} == wanted, "dismissal methods missing")
    subject = ast.ClassDef(
        name="DismissalSubject",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[subject], type_ignores=[]))
    namespace = {"GLib": FakeGLib}
    exec(compile(module, str(MANAGER), "exec"), namespace)
    return namespace["DismissalSubject"]


class FakeApp:
    def __init__(self):
        self.hidden = 0

    def surface_hidden(self):
        self.hidden += 1


def instance():
    subject = subject_type()()
    subject._dismiss_source_id = 0
    subject._visibility_generation = 10
    subject._destroyed = False
    subject.visible = True
    subject.surface_mode = "drawer"
    subject.capture = []
    subject.flushes = 0
    subject.destroys = 0
    subject.app = FakeApp()

    subject.get_visible = lambda: subject.visible
    subject.set_visible = lambda value: setattr(subject, "visible", value)
    subject._set_keyboard_capture = lambda enabled: subject.capture.append(enabled)
    subject._flush_pending_theme_sway_reload = (
        lambda: setattr(subject, "flushes", subject.flushes + 1)
    )
    subject.get_application = lambda: subject.app

    def destroy():
        subject.destroys += 1
        subject._on_destroyed()

    subject.destroy = destroy
    return subject


def main():
    FakeGLib.reset()
    subject = instance()
    require(subject._defer_input_dismissal(), "first dismissal was not handled")
    first_id = subject._dismiss_source_id
    require(first_id in FakeGLib.callbacks, "idle dismissal was not queued")
    require(subject._defer_input_dismissal(), "duplicate dismissal not handled")
    require(subject._dismiss_source_id == first_id, "duplicate was not coalesced")

    callback, args = FakeGLib.callbacks[first_id]
    callback(*args)
    require(not subject.visible, "real close_surface did not hide drawer")
    require(subject.capture == [False], "real close did not release capture")
    require(subject.flushes == 1, "theme flush path did not run exactly once")
    require(subject.app.hidden == 1, "surface_hidden did not run exactly once")
    require(subject.destroys == 1, "drawer was not destroyed exactly once")
    require(subject._destroyed, "destroy state was not recorded")

    subject.close_surface()
    require(subject.capture == [False], "repeated close was not idempotent")
    require(subject.flushes == 1, "repeated close repeated theme side effects")
    require(subject.app.hidden == 1, "repeated close repeated app side effects")
    require(subject.destroys == 1, "repeated close destroyed twice")

    FakeGLib.reset()
    subject = instance()
    subject._defer_input_dismissal()
    stale_id = subject._dismiss_source_id
    stale_callback, stale_args = FakeGLib.callbacks[stale_id]

    old_generation = subject._visibility_generation
    subject._prepare_show()
    require(subject._visibility_generation > old_generation, "reopen did not advance generation")
    require(stale_id in FakeGLib.removed, "reopen did not cancel callback A")

    subject._defer_input_dismissal()
    live_id = subject._dismiss_source_id
    require(live_id != 0 and live_id != stale_id, "callback B was not queued")

    stale_callback(*stale_args)
    require(subject._dismiss_source_id == live_id, "stale callback A erased live callback B")
    subject._defer_input_dismissal()
    require(subject._dismiss_source_id == live_id, "duplicate callback B was not coalesced")

    live_callback, live_args = FakeGLib.callbacks[live_id]
    live_callback(*live_args)
    require(not subject.visible, "live callback B did not close the drawer")
    require(subject.destroys == 1, "live callback B did not destroy once")

    FakeGLib.reset()
    subject = instance()
    subject._defer_input_dismissal()
    stale_id = subject._dismiss_source_id
    callback, args = FakeGLib.callbacks[stale_id]
    subject._on_destroyed()
    callback(*args)
    require(subject.destroys == 0, "stale destroyed callback caused destruction")
    require(subject.visible, "stale destroyed callback changed visibility")
    require(subject._defer_input_dismissal(), "destroyed input was not consumed")
    require(not FakeGLib.callbacks, "destroyed surface queued new callback")

    FakeGLib.reset()
    subject = instance()
    subject._defer_escape_dismissal()
    first_id = subject._dismiss_source_id
    subject._defer_input_dismissal()
    require(subject._dismiss_source_id == first_id, "Escape and click paths do not coalesce")

    print("HyperLab drawer dismissal behavioral contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
