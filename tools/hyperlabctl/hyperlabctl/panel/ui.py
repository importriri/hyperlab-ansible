"""Painting the screen model with curses. Decisions live in model.py.

Catppuccin Mocha exactly when the terminal can redefine colours, and the
nearest 256-colour approximations when it cannot. foot can.
"""

import curses

MOCHA = {
    "base": (0x1e, 0x1e, 0x2e), "surface1": (0x45, 0x47, 0x5a),
    "text": (0xcd, 0xd6, 0xf4), "overlay": (0x6c, 0x70, 0x86),
    "green": (0xa6, 0xe3, 0xa1), "yellow": (0xf9, 0xe2, 0xaf),
    "red": (0xf3, 0x8b, 0xa8), "blue": (0x89, 0xb4, 0xfa),
    "mauve": (0xcb, 0xa6, 0xf7), "peach": (0xfa, 0xb3, 0x87),
}
FALLBACK = {"base": 235, "surface1": 238, "text": 189, "overlay": 243,
            "green": 151, "yellow": 223, "red": 210, "blue": 111,
            "mauve": 183, "peach": 216}
TONES = {"ok": "green", "warn": "yellow", "error": "red", "dim": "overlay",
         "mauve": "mauve", "accent": "blue", "text": "text", "peach": "peach"}
BOX = {"h": "─", "v": "│", "tl": "┌", "tr": "┐", "bl": "└", "br": "┘"}

PAIRS = {}


def setup_colors():
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    slots = {}
    changeable = curses.can_change_color() and curses.COLORS >= 32
    for index, (name, rgb) in enumerate(MOCHA.items(), start=16):
        if changeable:
            curses.init_color(index, *[int(channel / 255 * 1000) for channel in rgb])
            slots[name] = index
        else:
            slots[name] = FALLBACK[name]
    for number, (name, colour) in enumerate(TONES.items(), start=1):
        curses.init_pair(number, slots[colour], -1)
        PAIRS[name] = curses.color_pair(number)
    curses.init_pair(30, slots["base"], slots["blue"])
    PAIRS["header"] = curses.color_pair(30)
    curses.init_pair(31, slots["text"], slots["surface1"])
    PAIRS["selected"] = curses.color_pair(31)
    curses.init_pair(32, slots["base"], slots["mauve"])
    PAIRS["tab"] = curses.color_pair(32)


def tone(name, bold=False):
    return PAIRS.get(name, PAIRS.get("text", 0)) | (curses.A_BOLD if bold else 0)


def _put(window, y, x, text, attribute=0, width=None):
    height, columns = window.getmaxyx()
    if y < 0 or y >= height or x >= columns or x < 0:
        return
    room = (columns - x - 1) if width is None else min(width, columns - x - 1)
    if room <= 0:
        return
    try:
        window.addnstr(y, x, str(text), room, attribute)
    except curses.error:
        pass


def _box(window, top, left, height, width, title="", attribute=None):
    attribute = attribute if attribute is not None else tone("dim")
    _put(window, top, left, BOX["tl"] + BOX["h"] * (width - 2) + BOX["tr"], attribute, width)
    for offset in range(1, height - 1):
        _put(window, top + offset, left, BOX["v"], attribute)
        _put(window, top + offset, left + width - 1, BOX["v"], attribute)
    _put(window, top + height - 1, left,
         BOX["bl"] + BOX["h"] * (width - 2) + BOX["br"], attribute, width)
    if title:
        _put(window, top, left + 2, " %s " % title, tone("mauve", True))


def draw(window, screen):
    window.erase()
    height, columns = window.getmaxyx()

    if screen["too_small"]:
        _put(window, 0, 0, "terminal too small: need at least %dx%d" % screen["minimum"],
             tone("warn", True))
        window.noutrefresh()
        return

    header = screen["header"]
    _put(window, 0, 0, " " * (columns - 1), tone("header"))
    _put(window, 0, 1, header["left"], tone("header", True))
    _put(window, 0, 11, header["middle"], tone("header"))
    _put(window, 0, max(12, columns - len(header["right"]) - 2), header["right"], tone("header"))

    span = max(18, (columns - 2) // len(screen["tiles"]))
    for index, tile in enumerate(screen["tiles"]):
        left = 1 + index * span
        _put(window, 2, left, tile["label"], tone("dim"), span - 1)
        _put(window, 3, left, tile["value"], tone(tile["tone"], True), span - 1)
        if tile["gauge"]:
            _put(window, 4, left, tile["gauge"], tone(tile["tone"]), span - 1)

    offset = 1
    for tab in screen["tabs"]:
        label = " %d %s %d " % (tab["index"], tab["title"], tab["count"])
        _put(window, 6, offset, label, tone("tab", True) if tab["active"] else tone("dim"))
        offset += len(label) + 1

    wide = screen["layout"] == "wide"
    detail_width = 34 if wide else 0
    table_width = columns - 2 - detail_width - (1 if wide else 0)
    table_top = 8
    problem_rows = len(screen["problems"]) * 2
    table_height = max(5, height - table_top - problem_rows - 3)

    _box(window, table_top, 1, table_height, table_width, screen["view"])
    inner = table_top + 1
    position = 2
    for label, size, _key in screen["columns"]:
        _put(window, inner, position, label.upper(), tone("dim"),
             (size - 1) if size else table_width - position - 2)
        position += size if size else 0
    inner += 1

    visible = table_height - 3
    first = max(0, screen["selected"] - visible + 1) if screen["selected"] >= visible else 0
    for index, row in enumerate(screen["rows"][first:first + visible]):
        actual = first + index
        chosen = actual == screen["selected"]
        line = inner + index
        if chosen:
            _put(window, line, 2, " " * (table_width - 3), tone("selected"))
        position = 2
        for _label, size, key in screen["columns"]:
            if chosen:
                attribute = tone("selected", key == "name")
            elif key == "name":
                attribute = tone("text")
            elif key == "note":
                attribute = tone(row["tone"])
            else:
                attribute = tone("ok" if row["running"] else "dim")
            _put(window, line, position, row[key], attribute,
                 (size - 1) if size else table_width - position - 2)
            position += size if size else 0

    if wide:
        left = 1 + table_width + 1
        _box(window, table_top, left, table_height, detail_width, "detail")
        row = screen["selected_row"]
        line = table_top + 1
        if row:
            _put(window, line, left + 2, row["name"], tone("mauve", True), detail_width - 4)
            line += 2
            for label, value in row["detail"]:
                _put(window, line, left + 2, label, tone("dim"), detail_width - 4)
                _put(window, line + 1, left + 2, value, tone("text"), detail_width - 4)
                line += 2
        else:
            _put(window, line, left + 2, "nothing here", tone("dim"))

    line = table_top + table_height
    for problem in screen["problems"]:
        _put(window, line, 1, "%-5s %s" % (problem["severity"], problem["message"]),
             tone(problem["severity"]))
        line += 1
        if problem["remedy"]:
            _put(window, line, 7, "fix: %s" % problem["remedy"], tone("dim"))
        line += 1

    if screen["filter"]:
        _put(window, height - 2, 1, "filter: %s" % screen["filter"], tone("peach"))

    _put(window, height - 1, 0, " " * (columns - 1), tone("selected"))
    position = 1
    for item in screen["footer"]:
        _put(window, height - 1, position, item["key"],
             tone("peach", True) if item["enabled"] else tone("dim"))
        _put(window, height - 1, position + len(item["key"]) + 1, item["label"],
             tone("selected") if item["enabled"] else tone("dim"))
        position += len(item["key"]) + len(item["label"]) + 4

    if screen["overlay"]:
        _overlay(window, screen["overlay"])
    window.noutrefresh()


def _overlay(window, panel):
    height, columns = window.getmaxyx()
    lines = panel["lines"]
    box_height = min(len(lines) + 4, height - 4)
    box_width = min(64, columns - 6)
    top = max(1, (height - box_height) // 2)
    left = max(1, (columns - box_width) // 2)
    for offset in range(box_height):
        _put(window, top + offset, left, " " * box_width, tone("selected"))
    _box(window, top, left, box_height, box_width, panel["title"], tone("mauve"))
    for index, (label, value) in enumerate(lines[:box_height - 4]):
        _put(window, top + 2 + index, left + 2, "%-9s" % label, tone("peach"), 10)
        _put(window, top + 2 + index, left + 13, value, tone("text"), box_width - 15)
