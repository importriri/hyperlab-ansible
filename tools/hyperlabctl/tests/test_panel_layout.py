"""Layout, gauge and overlays: still pure data, still no terminal."""

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.panel import model

DOMAINS = [{"name": "win11clean-valley", "state": "running", "memory_mb": 6144, "vfio": True},
           {"name": "debian-dev", "state": "shut off", "memory_mb": 1024, "network": "dev"}]


def _screen(**kwargs):
    built = document.build(world.build(domains=DOMAINS, trust=3))
    return model.build_screen(built, **kwargs)


def test_layout_switches_to_two_panes_only_when_there_is_room():
    equals("narrow_layout", _screen(width=100)["layout"], "narrow")
    equals("wide_layout", _screen(width=130)["layout"], "wide")


def test_gauge_is_the_requested_width_at_every_fraction():
    for fraction in (0.0, 0.01, 0.5, 0.99, 1.0, 2.0, -1.0):
        equals("gauge_width_%s" % fraction, len(model.gauge(fraction, 14)), 14)


def test_gauge_is_empty_at_zero_and_full_at_one():
    equals("gauge_zero", model.gauge(0.0, 6), "······")
    equals("gauge_one", model.gauge(1.0, 6), "██████")


def test_the_ram_tile_carries_a_gauge_and_the_gpu_tile_does_not():
    tiles = {tile["label"]: tile for tile in _screen()["tiles"]}
    check("ram_has_gauge", tiles["assignable ram"]["gauge"] is not None)
    check("gpu_has_no_gauge", tiles["gpu"]["gauge"] is None)


def test_help_overlay_lists_every_key_the_footer_offers():
    screen = _screen(overlay="help")
    equals("overlay_kind", screen["overlay"]["kind"], "help")
    listed = {key for key, _text in screen["overlay"]["lines"]}
    for item in screen["footer"]:
        if item["key"] in ("s", "x", "i", "/", "r", "?", "q"):
            check("help_documents_%s" % item["key"],
                  any(item["key"] in key for key in listed))


def test_inspect_overlay_describes_the_selected_row():
    screen = _screen(overlay="inspect", selected=1)
    equals("inspect_title", screen["overlay"]["title"], "debian-dev")
    check("inspect_has_lines", len(screen["overlay"]["lines"]) > 0)


def test_inspect_overlay_is_absent_when_nothing_is_selected():
    built = document.build(world.build(domains=[], trust=None))
    screen = model.build_screen(built, overlay="inspect")
    equals("no_overlay_without_a_row", screen["overlay"], None)


def test_filter_matches_the_note_as_well_as_the_name():
    equals("filter_by_note", len(_screen(filter_text="vfio")["rows"]), 1)
    equals("filter_by_name", len(_screen(filter_text="debian")["rows"]), 1)
    equals("filter_misses", len(_screen(filter_text="zzz")["rows"]), 0)
