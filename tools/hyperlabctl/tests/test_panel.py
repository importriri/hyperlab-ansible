"""The panel's decisions live in the model, so this is where they are checked."""

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.panel import model

RUNNING_VFIO = [{"name": "win11clean-valley", "state": "running",
                 "memory_mb": 6144, "vfio": True}]
MIXED = [{"name": "debian-dev", "state": "running", "memory_mb": 1024, "network": "dev"},
         {"name": "fedora-dev", "state": "shut off", "memory_mb": 4096, "network": "dev"},
         {"name": "parrot-disposable", "state": "shut off", "memory_mb": 1024,
          "network": "lab"}]


def _screen(domains, trust=None, **kwargs):
    built = document.build(world.build(domains=domains, trust=trust))
    return model.build_screen(built, **kwargs)


def test_screen_reports_four_tiles_in_a_fixed_order():
    equals("tile_labels", [tile["label"] for tile in _screen(MIXED)["tiles"]],
           ["trust", "assignable ram", "gpu", "networks"])


def test_tiles_go_red_when_a_section_could_not_be_read():
    built = document.build(world.build(trust=None, profile_report=False))
    tones = {tile["label"]: tile["tone"] for tile in model.build_screen(built)["tiles"]}
    equals("ram_tile_error", tones["assignable ram"], "error")
    equals("gpu_tile_error", tones["gpu"], "error")
    equals("networks_tile_ok", tones["networks"], "ok")


def test_selection_is_clamped_to_the_rows_that_exist():
    screen = _screen(MIXED, selected=99)
    equals("selection_clamped", screen["selected"], len(screen["rows"]) - 1)


def test_selection_on_an_empty_table_is_zero_and_row_is_none():
    screen = _screen([], selected=4)
    equals("empty_selection", screen["selected"], 0)
    equals("empty_selected_row", screen["selected_row"], None)


def test_filter_narrows_the_rows_without_touching_the_document():
    screen = _screen(MIXED, filter_text="parrot")
    equals("filtered_count", len(screen["rows"]), 1)
    equals("filtered_name", screen["rows"][0]["name"], "parrot-disposable")


def test_footer_disables_start_on_a_running_domain():
    footer = {item["key"]: item["enabled"] for item in _screen(MIXED, selected=0)["footer"]}
    equals("start_disabled_when_running", footer["s"], False)
    equals("stop_enabled_when_running", footer["x"], True)


def test_footer_disables_start_on_a_blocked_domain():
    screen = _screen(RUNNING_VFIO + MIXED[1:2], trust=3, selected=1)
    equals("selected_is_fedora", screen["selected_row"]["name"], "fedora-dev")
    footer = {item["key"]: item["enabled"] for item in screen["footer"]}
    equals("start_disabled_when_blocked", footer["s"], False)


def test_footer_enables_start_on_a_stopped_domain_that_fits():
    screen = _screen(MIXED, selected=2)
    equals("selected_is_parrot", screen["selected_row"]["name"], "parrot-disposable")
    footer = {item["key"]: item["enabled"] for item in screen["footer"]}
    equals("start_enabled_when_it_fits", footer["s"], True)


def test_unguarded_vfio_row_is_marked_in_the_note():
    screen = _screen([{"name": "rogue-vfio", "state": "running",
                       "memory_mb": 1024, "vfio": True}])
    equals("unguarded_note", screen["rows"][0]["note"], "vfio UNGUARDED")
    equals("unguarded_tone", screen["rows"][0]["tone"], "error")


def test_guarded_vfio_row_names_its_trust_profile():
    equals("guarded_note", _screen(RUNNING_VFIO, trust=3)["rows"][0]["note"], "vfio clean")


def test_every_problem_carries_a_remedy():
    built = document.build(world.build(trust=None, profile_report=False))
    screen = model.build_screen(built)
    check("problems_present", len(screen["problems"]) > 0)
    for problem in screen["problems"]:
        check("remedy_for_%s" % problem["message"][:20], problem["remedy"] is not None)


def test_a_small_terminal_is_refused_rather_than_drawn_badly():
    equals("too_small", _screen(MIXED, width=40, height=10)["too_small"], True)
    equals("big_enough", _screen(MIXED, width=120, height=40)["too_small"], False)
