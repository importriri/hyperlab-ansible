"""Minimal GTK4 stub for validating the widget-tree structure.

It draws nothing and does not pretend otherwise. Widgets are replaced with
objects that record orientation, CSS classes, children, and ordering. This is
enough to answer the questions that matter without a display — is the domain
column on the left? is the right rail really attached? — by executing rather
than guessing from source.
"""
from __future__ import annotations

import sys
import types


class _Enum:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"<{self.name}>"


class Orientation:
    HORIZONTAL = _Enum("HORIZONTAL")
    VERTICAL = _Enum("VERTICAL")


class PolicyType:
    NEVER = _Enum("NEVER")
    AUTOMATIC = _Enum("AUTOMATIC")
    ALWAYS = _Enum("ALWAYS")


class Align:
    START = _Enum("START")
    END = _Enum("END")
    CENTER = _Enum("CENTER")
    FILL = _Enum("FILL")


class Widget:
    def __init__(self, **kwargs) -> None:
        self.props = dict(kwargs)
        self.orientation = kwargs.get("orientation")
        self.spacing = kwargs.get("spacing")
        self.label = kwargs.get("label")
        self.css = []
        self.children = []
        self.parent = None
        self.hexpand = False
        self.vexpand = False
        self.size_request = None
        self.signals = {}
        self.tooltip = None
        self.sensitive = True
        self.child = None
        self.visible = True

    # --- structure
    def append(self, child):
        child.parent = self
        self.children.append(child)

    def prepend(self, child):
        child.parent = self
        self.children.insert(0, child)

    def remove(self, child):
        if child in self.children:
            child.parent = None
            self.children.remove(child)

    def get_first_child(self):
        return self.children[0] if self.children else None

    def get_next_sibling(self):
        if self.parent is None:
            return None
        siblings = self.parent.children
        i = siblings.index(self)
        return siblings[i + 1] if i + 1 < len(siblings) else None

    def set_child(self, child):
        self.child = child
        if child is not None:
            child.parent = self
            self.children = [child]

    def get_child(self):
        return self.child

    # --- proprieta'
    def add_css_class(self, name): self.css.append(name)
    def remove_css_class(self, name):
        if name in self.css:
            self.css.remove(name)
    def has_css_class(self, name): return name in self.css
    def set_hexpand(self, value): self.hexpand = value
    def set_vexpand(self, value): self.vexpand = value
    def set_size_request(self, width, height): self.size_request = (width, height)
    def set_tooltip_text(self, text): self.tooltip = text
    def set_sensitive(self, value): self.sensitive = value
    def set_visible(self, value): self.visible = value
    def set_wrap(self, value): self.props["wrap"] = value
    def set_selectable(self, value): self.props["selectable"] = value
    def set_xalign(self, value): self.props["xalign"] = value
    def set_ellipsize(self, value): self.props["ellipsize"] = value
    def set_pixel_size(self, value): self.props["pixel_size"] = value
    def set_placeholder_text(self, text): self.props["placeholder"] = text
    def set_text(self, text): self.label = text
    def get_text(self): return self.label or ""
    def set_label(self, text): self.label = text
    def get_label(self): return self.label
    def set_policy(self, h, v): self.props["policy"] = (h, v)
    def set_orientation(self, value): self.orientation = value
    def set_homogeneous(self, v): self.props["homogeneous"] = v
    def set_spacing(self, v): self.spacing = v
    def set_selection_mode(self, v): self.props["selection_mode"] = v
    def set_show_separators(self, v): self.props["separators"] = v
    def set_activate_on_single_click(self, v): self.props["single_click"] = v
    def set_halign(self, value): self.props["halign"] = value
    def set_valign(self, value): self.props["valign"] = value
    def set_margin_top(self, v): self.props["margin_top"] = v
    def set_margin_bottom(self, v): self.props["margin_bottom"] = v
    def set_margin_start(self, v): self.props["margin_start"] = v
    def set_margin_end(self, v): self.props["margin_end"] = v
    def connect(self, signal, callback, *args):
        self.signals.setdefault(signal, []).append(callback)
        return len(self.signals[signal])
    def emit(self, signal, *args):
        for callback in self.signals.get(signal, []):
            callback(self, *args)

    # --- comodita' per i test
    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def texts(self):
        return [w.label for w in self.walk() if w.label]

    def __repr__(self) -> str:
        tag = "/".join(self.css) or type(self).__name__
        return f"<{tag} {self.orientation.name if self.orientation else ''} n={len(self.children)}>"


class Box(Widget): pass
class Button(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "child" in kwargs:
            self.set_child(kwargs["child"])
class Label(Widget): pass
class SearchEntry(Widget): pass
class ScrolledWindow(Widget): pass
class Separator(Widget): pass
class Grid(Widget):
    def attach(self, child, col, row, w, h):
        self.props.setdefault("cells", []).append((col, row, w, h))
        self.append(child)
    def set_column_homogeneous(self, v): self.props["col_homog"] = v
    def set_row_homogeneous(self, v): self.props["row_homog"] = v
    def set_column_spacing(self, v): self.props["col_spacing"] = v
    def set_row_spacing(self, v): self.props["row_spacing"] = v
    def get_child_at(self, col, row): return None
class Image(Widget):
    @staticmethod
    def new_from_file(path):
        item = Image()
        item.props["file"] = path
        return item
    @staticmethod
    def new_from_icon_name(name):
        item = Image()
        item.props["icon"] = name
        return item
class Window(Widget): pass
class ListBox(Widget): pass
class ListBoxRow(Widget): pass
class Stack(Widget): pass
class Entry(Widget):
    def set_editable(self, v): self.props["editable"] = v
class DropDown(Widget):
    @staticmethod
    def new_from_strings(items):
        d = DropDown()
        d.props["items"] = list(items) if items is not None else []
        d.props["selected"] = 0
        return d
    def set_selected(self, i): self.props["selected"] = i
    def get_selected(self): return self.props.get("selected", 0)
    def get_selected_item(self):
        items = self.props.get("items") or []
        index = self.props.get("selected", 0)
        item = items[index] if index < len(items) else None
        return type("StringObject", (), {"get_string": lambda s, v=item: v})()
    def get_model(self):
        return self.props.get("items") or []
    def set_model(self, model):
        self.props["items"] = list(model) if model is not None else []
class CheckButton(Widget):
    def set_active(self, v): self.props["active"] = v
    def get_active(self): return bool(self.props.get("active"))
class Switch(Widget):
    def set_active(self, v): self.props["active"] = v
    def get_active(self): return bool(self.props.get("active"))
class SpinButton(Widget):
    @staticmethod
    def new_with_range(lo, hi, step):
        s = SpinButton(); s.props["range"] = (lo, hi, step); s.props["value"] = lo
        return s
    def set_value(self, v): self.props["value"] = v
    def get_value(self): return self.props.get("value", 0)
    def get_value_as_int(self): return int(self.props.get("value", 0))
class Revealer(Widget): pass


def install() -> None:
    """Register fake modules before the manager imports them."""
    gtk = types.ModuleType("Gtk")
    for name, value in globals().items():
        if isinstance(value, type) and issubclass(value, Widget):
            setattr(gtk, name, value)
    gtk.Orientation = Orientation
    gtk.PolicyType = PolicyType
    gtk.Align = Align
    gtk.INVALID_LIST_POSITION = 4294967295
    gtk.SelectionMode = type("SelectionMode", (), {
        "NONE": _Enum("NONE"), "SINGLE": _Enum("SINGLE"),
        "BROWSE": _Enum("BROWSE"), "MULTIPLE": _Enum("MULTIPLE")})
    class StringList(Widget):
        def __init__(self, strings=()):
            Widget.__init__(self)
            self.props["items"] = list(strings or [])
        def append(self, s): self.props["items"].append(s)
        def get_n_items(self): return len(self.props.get("items", []))
        def get_string(self, i): return self.props["items"][i]
        def __iter__(self):
            return iter(self.props["items"])
        def __len__(self):
            return len(self.props["items"])
        def get_item(self, i):
            value = self.props["items"][i]
            return type("StringObject", (), {"get_string": lambda s: value})()
    gtk.StringList = StringList
    def _stringlist_new(strings=()):
        item = gtk.StringList(); item.props["items"] = list(strings or []); return item
    gtk.StringList.new = staticmethod(_stringlist_new)
    gtk.Orientation = Orientation
    gtk.Widget = Widget
    gtk.Application = type("Application", (Widget,), {})
    gtk.CssProvider = type("CssProvider", (Widget,), {
        "load_from_data": lambda self, *a: None,
        "load_from_string": lambda self, *a: None,
    })
    gtk.StyleContext = type("StyleContext", (), {
        "add_provider_for_display": staticmethod(lambda *a: None)})
    gtk.STYLE_PROVIDER_PRIORITY_APPLICATION = 600
    gtk.EventControllerKey = type("EventControllerKey", (Widget,), {})
    for extra in ("GestureClick", "GestureLongPress", "EventControllerMotion",
                  "EventControllerScroll", "EventControllerFocus", "DropTarget"):
        setattr(gtk, extra, type(extra, (Widget,), {
            "set_button": lambda self, n: None,
            "set_propagation_phase": lambda self, p: None,
        }))
    Widget.add_controller = lambda self, controller: self.props.setdefault(
        "controllers", []).append(controller)
    gtk.ShortcutController = type("ShortcutController", (Widget,), {})

    gdk = types.ModuleType("Gdk")
    gdk.Display = type("Display", (), {"get_default": staticmethod(lambda: None)})

    gio = types.ModuleType("Gio")
    gio.ApplicationFlags = type("ApplicationFlags", (), {"HANDLES_COMMAND_LINE": 1})

    glib = types.ModuleType("GLib")
    glib.idle_add = lambda fn, *a: fn(*a)
    glib.timeout_add = lambda ms, fn, *a: 0

    layer = types.ModuleType("Gtk4LayerShell")
    for name in ("init_for_window", "set_layer", "set_anchor",
                 "set_keyboard_mode", "set_namespace", "set_margin",
                 "auto_exclusive_zone_enable"):
        setattr(layer, name, lambda *a, **k: None)
    layer.Layer = type("Layer", (), {"TOP": 1, "OVERLAY": 2})
    layer.Edge = type("Edge", (), {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3})
    layer.KeyboardMode = type("KeyboardMode", (), {"EXCLUSIVE": 1, "ON_DEMAND": 2})

    repository = types.ModuleType("gi.repository")
    for name, module in (("Gtk", gtk), ("Gdk", gdk), ("Gio", gio),
                         ("GLib", glib), ("Gtk4LayerShell", layer)):
        setattr(repository, name, module)
        sys.modules[f"gi.repository.{name}"] = module

    gi = types.ModuleType("gi")
    gi.require_version = lambda *a, **k: None
    gi.repository = repository
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository

    # the manager loads libgtk4-layer-shell with CDLL before importing gi
    import ctypes
    original = ctypes.CDLL
    def fake(name, *args, **kwargs):
        if "layer-shell" in str(name):
            return types.SimpleNamespace()
        return original(name, *args, **kwargs)
    ctypes.CDLL = fake
