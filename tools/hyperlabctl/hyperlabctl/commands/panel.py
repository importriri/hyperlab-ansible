import curses

from .. import document as doc
from ..errors import HyperlabError
from ..journal import read as read_journal
from ..operations import start, stop
from ..panel import model, ui
from ..panel.views import views
from .base import Command


class PanelCommand(Command):
    name = "panel"
    help = "the full screen cockpit"
    order = 5

    def configure(self, parser):
        parser.add_argument("--refresh", type=int, default=10, metavar="SECONDS",
                            help="automatic refresh; 0 disables it")
        parser.add_argument("--view", default="domains",
                            help="which view to open on")

    def run(self, args, ctx):
        try:
            curses.wrapper(self._loop, args, ctx)
        except HyperlabError as exc:
            print("hyperlabctl: %s" % exc)
            return 2
        return 0

    def _gather(self, ctx):
        ctx.cache.clear()
        document = doc.build(ctx)
        try:
            logs = read_journal(ctx, lines=60)
        except HyperlabError as exc:
            logs = [{"time": "", "level": "warn", "unit": "", "message": str(exc)}]
        return document, logs

    def _loop(self, window, args, ctx):
        curses.curs_set(0)
        ui.setup_colors()
        window.timeout(500)

        keys = [view.key for view in views()]
        view = args.view if args.view in keys else keys[0]
        document, logs = self._gather(ctx)
        selected, filter_text, overlay = 0, "", None
        message, ticks = None, 0

        while True:
            height, width = window.getmaxyx()
            screen = model.build_screen(document, logs, width, height,
                                        view, selected, filter_text, overlay)
            ui.draw(window, screen)
            if message:
                try:
                    window.addnstr(height - 2, 1, message[:width - 2], width - 2,
                                   ui.tone("peach", True))
                except curses.error:
                    pass
            curses.doupdate()

            key = window.getch()
            if key == -1:
                ticks += 1
                if args.refresh and ticks * 0.5 >= args.refresh:
                    document, logs = self._gather(ctx)
                    ticks = 0
                continue
            ticks = 0

            if overlay and key not in (curses.KEY_RESIZE,):
                overlay = None
                if key in (ord("q"), 27, ord("?"), ord("i")):
                    continue

            message = None
            if key in (ord("q"), 27):
                return
            if key == curses.KEY_RESIZE:
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                selected += 1
            elif key in (curses.KEY_UP, ord("k")):
                selected = max(0, selected - 1)
            elif key in (ord("\t"), curses.KEY_RIGHT):
                view = keys[(keys.index(view) + 1) % len(keys)]
                selected = 0
            elif key == curses.KEY_LEFT:
                view = keys[(keys.index(view) - 1) % len(keys)]
                selected = 0
            elif ord("1") <= key <= ord("9") and key - ord("1") < len(keys):
                view = keys[key - ord("1")]
                selected = 0
            elif key == ord("r"):
                document, logs = self._gather(ctx)
                message = "refreshed"
            elif key == ord("?"):
                overlay = "help"
            elif key == ord("i") and screen["selected_row"]:
                overlay = "inspect"
            elif key == ord("/"):
                filter_text = self._prompt(window, "filter: ")
                selected = 0
            elif key in (ord("s"), ord("x")) and screen["selected_row"]:
                message = self._move(ctx, screen, key)
                document, logs = self._gather(ctx)

    def _move(self, ctx, screen, key):
        row = screen["selected_row"]
        allowed = {item["key"]: item["enabled"] for item in screen["footer"]}
        wanted = "s" if key == ord("s") else "x"
        if not allowed.get(wanted):
            return "%s cannot %s from here" % (row["name"],
                                               "start" if wanted == "s" else "stop")
        outcome = start(ctx, row["name"]) if wanted == "s" else stop(ctx, row["name"])
        return outcome.message

    def _prompt(self, window, label):
        height, width = window.getmaxyx()
        curses.echo()
        curses.curs_set(1)
        window.timeout(-1)
        try:
            window.addnstr(height - 2, 1, label + " " * (width - len(label) - 3),
                           width - 2, ui.tone("peach"))
            typed = window.getstr(height - 2, 1 + len(label), 40)
        except curses.error:
            typed = b""
        finally:
            curses.noecho()
            curses.curs_set(0)
            window.timeout(500)
        return typed.decode("utf-8", "replace").strip()
