"""Every pill of the drawer must carry the same four keys as the summary."""

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.commands.waybar import FIELDS
from hyperlabctl.render import waybar_field

RUNNING_VFIO = [{"name": "win11clean-valley", "state": "running",
                 "memory_mb": 6144, "vfio": True}]


def test_every_field_returns_the_same_four_keys():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    for field in FIELDS:
        if field == "summary":
            continue
        payload = waybar_field(built, field)
        equals("keys_of_%s" % field, sorted(payload), ["alt", "class", "text", "tooltip"])


def test_ram_pill_goes_error_when_the_budget_is_blown():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    equals("ram_class", waybar_field(built, "ram")["class"], "error")


def test_gpu_pill_names_the_holder():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    equals("gpu_text", waybar_field(built, "gpu")["text"], "win11clean-valley")


def test_vms_pill_counts_running_over_total():
    domains = RUNNING_VFIO + [{"name": "debian-dev", "state": "shut off",
                               "memory_mb": 1024, "network": "dev"}]
    built = document.build(world.build(domains=domains, trust=3))
    equals("vms_text", waybar_field(built, "vms")["text"], "1/2")


def test_an_unreadable_section_makes_its_pill_red_and_points_at_doctor():
    built = document.build(world.build(trust=None, profile_report=False))
    payload = waybar_field(built, "gpu")
    equals("unreadable_class", payload["class"], "error")
    check("points_at_doctor", "doctor" in payload["tooltip"])
