"""Each view turns the document into rows. Adding a view adds a tab by itself."""

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.panel import model
from hyperlabctl.panel.views import View, views

DOMAINS = [{"name": "win11clean-valley", "state": "running", "memory_mb": 6144, "vfio": True},
           {"name": "debian-dev", "state": "shut off", "memory_mb": 1024, "network": "dev"}]


def _doc(**kwargs):
    return document.build(world.build(**kwargs))


def test_every_view_declares_columns_and_a_title():
    for view in views():
        check("view_%s_has_title" % view.key, bool(view.title))
        check("view_%s_has_columns" % view.key, len(view.columns) > 0)


def test_every_view_survives_a_fully_degraded_document():
    built = _doc(trust=None, profile_report=False)
    for view in views():
        rows = view.rows(built, [])
        check("view_%s_returned_a_list" % view.key, isinstance(rows, list))


def test_every_row_carries_the_keys_its_columns_ask_for():
    built = _doc(domains=DOMAINS, trust=3)
    for view in views():
        for row in view.rows(built, [{"time": "1", "level": "info", "message": "x"}]):
            for _label, _size, key in view.columns:
                check("view_%s_row_has_%s" % (view.key, key), key in row)


def test_a_view_that_cannot_act_reports_no_actions():
    built = _doc(domains=DOMAINS, trust=3)
    network_view = [view for view in views() if view.key == "networks"][0]
    row = network_view.rows(built, [])[0]
    equals("networks_cannot_start", network_view.actions(row)["start"], False)
    equals("networks_cannot_stop", network_view.actions(row)["stop"], False)


def test_tabs_count_the_rows_of_each_view():
    built = _doc(domains=DOMAINS, trust=3)
    screen = model.build_screen(built)
    counts = {tab["title"]: tab["count"] for tab in screen["tabs"]}
    equals("domains_tab_count", counts["domains"], 2)
    equals("networks_tab_count", counts["networks"], 5)


def test_switching_view_switches_columns_and_rows():
    built = _doc(domains=DOMAINS, trust=3)
    equals("domains_first_column",
           model.build_screen(built, view="domains")["columns"][0][0], "domain")
    equals("images_first_column",
           model.build_screen(built, view="images")["columns"][0][0], "image")


def test_an_unknown_view_falls_back_instead_of_raising():
    screen = model.build_screen(_doc(domains=DOMAINS, trust=3), view="nope")
    equals("fallback_view", screen["view"], "domains")


def test_a_view_registered_at_runtime_appears_in_the_tabs():
    class ContribView(View):
        key = "contrib"
        title = "contrib"
        order = 999
        columns = (("thing", 10, "name"),)

        def rows(self, document, logs):
            return [{"key": "a", "name": "a", "state": "-", "ram": "-",
                     "network": "-", "note": "", "tone": "dim", "running": False,
                     "blocked": None, "detail": []}]
    try:
        screen = model.build_screen(_doc(trust=None))
        check("contrib_tab_present",
              any(tab["title"] == "contrib" for tab in screen["tabs"]))
    finally:
        from hyperlabctl.panel.views import REGISTRY
        REGISTRY.pop("contrib", None)


def test_two_views_may_not_claim_the_same_key():
    from hyperlabctl.panel.views import DomainView
    try:
        class Clash(View):
            key = "domains"
            title = "clash"
            columns = (("a", 4, "name"),)

            def rows(self, document, logs):
                return []
        check("duplicate_view_key_refused", False, "no RuntimeError")
    except RuntimeError as exc:
        check("duplicate_view_key_message", "claim the key" in str(exc))
    finally:
        from hyperlabctl.panel.views import REGISTRY
        REGISTRY["domains"] = DomainView
