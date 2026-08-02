"""Document plus terminal size in, a screen of plain data out. No curses here.

Every decision the panel makes is taken in this module, which is why the panel
has tests: the suite asserts on the screen, and never has to drive a terminal.
"""

from ..remedies import remedy
from .views import views

MIN_WIDTH = 78
MIN_HEIGHT = 20
WIDE_AT = 118
GAUGE_BLOCKS = " ▏▎▍▌▋▊▉█"

HELP = [
    ("j / k", "move the selection"),
    ("tab", "next view"),
    ("1..5", "jump to a view"),
    ("s", "start the selected domain"),
    ("x", "shut the selected domain down"),
    ("i", "inspect: full detail for the row"),
    ("/", "filter by name"),
    ("r", "refresh now"),
    ("?", "this help"),
    ("q", "quit"),
]


def _tile(label, value, tone, gauge=None):
    return {"label": label, "value": value, "tone": tone, "gauge": gauge}


def gauge(fraction, width=14):
    """A block-glyph bar. Returned as text so the painter stays dumb."""
    fraction = max(0.0, min(1.0, fraction))
    exact = fraction * width
    full = int(exact)
    remainder = int(round((exact - full) * (len(GAUGE_BLOCKS) - 1)))
    bar = "█" * full
    if full < width and remainder:
        bar += GAUGE_BLOCKS[remainder]
    return bar.ljust(width, "·")


def tiles(document):
    built = []
    trust = document.get("trust")
    if trust is None:
        built.append(_tile("trust", "unknown", "error"))
    elif trust["claimed"]:
        built.append(_tile("trust", "%s / %s" % (trust["name"] or "?", trust["level"]), "warn"))
    else:
        built.append(_tile("trust", "unclaimed", "ok"))

    memory = document.get("memory")
    if memory is None:
        built.append(_tile("assignable ram", "unknown", "error"))
    else:
        total = memory["total_mb"] or 1
        used = total - memory["assignable_mb"]
        built.append(_tile("assignable ram", "%d MB" % memory["assignable_mb"],
                           "error" if memory["negative"] else "ok",
                           gauge(used / total)))

    gpu = document.get("gpu")
    if gpu is None:
        built.append(_tile("gpu", "unknown", "error"))
    elif gpu["held_by"]:
        built.append(_tile("gpu", gpu["held_by"], "warn"))
    else:
        built.append(_tile("gpu", "free" if gpu["bound"] else "not bound",
                           "ok" if gpu["bound"] else "warn"))

    networks = document.get("networks")
    if networks is None:
        built.append(_tile("networks", "unknown", "error"))
    else:
        complete = networks["active"] == networks["expected"]
        built.append(_tile("networks", "%d / %d" % (networks["active"], networks["expected"]),
                           "ok" if complete else "warn",
                           gauge(networks["active"] / max(networks["expected"], 1))))
    return built


def tabs(document, active):
    built = []
    for index, view in enumerate(views(), start=1):
        counts = len(view.rows(document, []))
        built.append({"key": view.key, "title": view.title, "index": index,
                      "active": view.key == active, "count": counts})
    return built


def footer(row, view):
    can = view.actions(row) if row else {"start": False, "stop": False}
    return [
        {"key": "s", "label": "start", "enabled": bool(can["start"])},
        {"key": "x", "label": "stop", "enabled": bool(can["stop"])},
        {"key": "i", "label": "inspect", "enabled": bool(row)},
        {"key": "tab", "label": "view", "enabled": True},
        {"key": "/", "label": "filter", "enabled": True},
        {"key": "r", "label": "refresh", "enabled": True},
        {"key": "?", "label": "help", "enabled": True},
        {"key": "q", "label": "quit", "enabled": True},
    ]


def problems(document, limit=3):
    listed = []
    for problem in (document.get("problems") or [])[:limit]:
        listed.append({"severity": problem["severity"], "message": problem["message"],
                       "remedy": remedy(problem, document)})
    return listed


def _view(key):
    for candidate in views():
        if candidate.key == key:
            return candidate
    return views()[0]


def build_screen(document, logs=None, width=100, height=32, view="domains",
                 selected=0, filter_text="", overlay=None):
    active = _view(view)
    rows = active.rows(document, logs or [])
    needle = filter_text.strip().lower()
    if needle:
        rows = [row for row in rows if needle in str(row["name"]).lower()
                or needle in str(row["note"]).lower()]
    selected = max(0, min(selected, len(rows) - 1)) if rows else 0
    row = rows[selected] if rows else None

    panel = None
    if overlay == "help":
        panel = {"kind": "help", "title": "keys", "lines": HELP}
    elif overlay == "inspect" and row:
        panel = {"kind": "inspect", "title": str(row["name"]), "lines": row["detail"]}

    host = document.get("host") or {}
    return {
        "too_small": width < MIN_WIDTH or height < MIN_HEIGHT,
        "minimum": (MIN_WIDTH, MIN_HEIGHT),
        "layout": "wide" if width >= WIDE_AT else "narrow",
        "header": {
            "left": "hyperlab",
            "middle": "%s  %s" % (host.get("hostname") or "?",
                                  host.get("profile") or "no profile"),
            "right": (document.get("generated_at") or "")[11:19],
        },
        "tiles": tiles(document),
        "tabs": tabs(document, active.key),
        "view": active.key,
        "columns": list(active.columns),
        "rows": rows,
        "selected": selected,
        "selected_row": row,
        "filter": filter_text,
        "overlay": panel,
        "problems": problems(document),
        "footer": footer(row, active),
    }
