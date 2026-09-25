"""Legacy status fields plus the explicit read-only C7 machine projection."""

import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.commands.waybar import FIELDS
from hyperlabctl.render import waybar_field

RUNNING_VFIO = [{"name": "win11clean-valley", "state": "running",
                 "memory_mb": 6144, "vfio": True}]


def test_every_field_preserves_status_keys_with_explicit_vms_extension():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    for field in FIELDS:
        if field == "summary":
            continue
        payload = waybar_field(built, field)
        expected = ["alt", "class", "text", "tooltip"]
        if field == "vms":
            expected += ["machines", "machines_available"]
        if field == "trust":
            expected += ["claimed", "identity", "known", "level"]
        if field == "gpu":
            expected += ["bound", "known", "owner"]
        equals("keys_of_%s" % field, sorted(payload), sorted(expected))
        for key in ("alt", "class", "text", "tooltip"):
            check("status_string_%s_%s" % (field, key), isinstance(payload[key], str))


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


def test_vms_projection_preserves_real_provider_facts():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    payload = waybar_field(built, "vms")
    equals("inventory_available", payload["machines_available"], True)
    equals("machine_count", len(payload["machines"]), 1)
    row = payload["machines"][0]
    equals("machine_projection_keys", sorted(row),
           ["blocked", "device_profile", "gpu", "gpu_relation", "lifecycle",
            "managed", "memory_mb", "name", "network", "networks",
            "provenance", "state", "vcpus", "vfio"])
    equals("machine_name", row["name"], "win11clean-valley")
    equals("machine_state", row["state"], "running")
    equals("machine_memory", row["memory_mb"], 6144)
    equals("machine_gpu_holder", row["gpu"], "GPU held")
    equals("machine_gpu_relation", row["gpu_relation"], "held")
    equals("machine_vfio", row["vfio"], True)


def test_vms_projection_separates_unknown_networks_from_no_networks():
    declared = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    row = waybar_field(declared, "vms")["machines"][0]
    check("declared_networks_is_a_list", isinstance(row["networks"], list))

    unreadable = waybar_field(
        {"domains": [{"name": "opaque", "state": "unknown",
                      "trust_profile": None, "networks": None}]},
        "vms",
    )["machines"][0]
    equals("unknown_networks_stay_null", unreadable["networks"], None)
    equals("unknown_network_stays_null", unreadable["network"], None)
    equals("unknown_gpu_relation", unreadable["gpu_relation"], "unknown")


def test_vms_projection_never_publishes_operation_capability():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    row = waybar_field(built, "vms")["machines"][0]
    for forbidden in ("capabilities", "verbs", "actions", "can_start"):
        check("no_%s_in_projection" % forbidden, forbidden not in row)


def test_vms_projection_distinguishes_failed_from_empty_inventory():
    failed = waybar_field({"domains": None}, "vms")
    empty = waybar_field({"domains": []}, "vms")
    equals("failed_inventory_available", failed["machines_available"], False)
    equals("failed_inventory_class", failed["class"], "error")
    equals("failed_inventory_count", failed["text"], "?")
    equals("empty_inventory_available", empty["machines_available"], True)
    equals("empty_inventory_count", empty["text"], "0/0")
    equals("failed_inventory_rows", failed["machines"], [])
    equals("empty_inventory_rows", empty["machines"], [])


def test_trust_projection_reports_the_explicit_claim_only():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    payload = waybar_field(built, "trust")
    equals("trust_claimed", payload["claimed"], True)
    equals("trust_identity", payload["identity"], "clean")
    equals("trust_level", payload["level"], 3)
    unclaimed = waybar_field(document.build(world.build(trust=None)), "trust")
    equals("unclaimed_claimed", unclaimed["claimed"], False)
    equals("unclaimed_identity", unclaimed["identity"], None)
    equals("unclaimed_level", unclaimed["level"], None)
    equals("unclaimed_known", unclaimed["known"], True)
    equals("claimed_known", payload["known"], True)


def test_trust_projection_never_turns_an_unreadable_claim_into_unclaimed():
    from hyperlabctl.render import trust_claim
    unreadable = waybar_field(document.build(world.build(trust="garbage")), "trust")
    equals("unreadable_known", unreadable["known"], False)
    equals("unreadable_claimed", unreadable["claimed"], False)
    check("unreadable_text_not_unclaimed", unreadable["text"] != "unclaimed")
    equals("unreadable_class", unreadable["class"], "error")
    unmapped = waybar_field(document.build(world.build(trust=7)), "trust")
    equals("unmapped_known", unmapped["known"], False)
    check("unmapped_text_not_unclaimed", unmapped["text"] != "unclaimed")
    cases = (
        ("missing_section", {}, False, False),
        ("section_not_object", {"trust": []}, False, False),
        ("empty_section", {"trust": {}}, False, False),
        ("claimed_not_bool", {"trust": {"claimed": "yes", "name": "dev", "level": 2}},
         False, False),
        ("services_claim", {"trust": {"claimed": True, "name": "services", "level": 2}},
         False, False),
        ("dev_wrong_rung", {"trust": {"claimed": True, "name": "dev", "level": 3}}, False, False),
        ("bool_rung", {"trust": {"claimed": True, "name": "dirty", "level": True}},
         False, False),
        ("valid_unclaimed", {"trust": {"claimed": False, "name": None, "level": None}},
         True, False),
        ("valid_dev", {"trust": {"claimed": True, "name": "dev", "level": 2}}, True, True),
        ("valid_lab", {"trust": {"claimed": True, "name": "lab", "level": 0}}, True, True),
    )
    for label, built, known, claimed in cases:
        projected = trust_claim(built)
        equals("claim_known_%s" % label, projected["known"], known)
        equals("claim_claimed_%s" % label, projected["claimed"], claimed)


def test_gpu_projection_names_the_real_owner_only():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    payload = waybar_field(built, "gpu")
    equals("gpu_owner", payload["owner"], "win11clean-valley")
    equals("gpu_known", payload["known"], True)
    unread = waybar_field(document.build(world.build(trust=None, profile_report=False)), "gpu")
    equals("gpu_unknown_owner", unread["owner"], None)
    equals("gpu_unknown", unread["known"], False)


def test_trust_provider_distinguishes_absence_from_read_failure():
    import errno
    import os
    from pathlib import Path
    from unittest import mock

    from hyperlabctl.render import as_waybar

    # 1. Genuine absence: the documented "never claimed since boot".
    absent = document.build(world.build(trust=None), only={"trust"})
    projected = waybar_field(absent, "trust")
    equals("absent_known", projected["known"], True)
    equals("absent_claimed", projected["claimed"], False)
    equals("absent_text", projected["text"], "unclaimed")
    equals("absent_no_problem", absent["problems"], [])

    # 2. A valid claim stays a valid claim.
    claimed = waybar_field(document.build(world.build(trust=2), only={"trust"}), "trust")
    equals("claimed_known", claimed["known"], True)
    equals("claimed_identity", claimed["identity"], "dev")
    equals("claimed_level", claimed["level"], 2)

    def failed(label, built):
        payload = waybar_field(built, "trust")
        equals("%s_section_null" % label, built["trust"], None)
        check("%s_problem_recorded" % label,
              any(problem.get("provider") == "trust" for problem in built["problems"]))
        equals("%s_known" % label, payload["known"], False)
        equals("%s_claimed" % label, payload["claimed"], False)
        equals("%s_identity" % label, payload["identity"], None)
        equals("%s_class" % label, payload["class"], "error")
        check("%s_never_unclaimed" % label, payload["text"] != "unclaimed")
        summary = as_waybar(built)
        check("%s_summary_never_unclaimed" % label, summary["text"] != "unclaimed")
        check("%s_summary_tooltip_unknown" % label,
              "trust: unclaimed" not in summary["tooltip"])
        return payload

    # 3. A real permission denial on an existing trust file.
    ctx = world.build(trust=2)
    trust_path = Path(ctx.config.gpu_handoff_state)
    if os.geteuid() != 0:
        trust_path.chmod(0)
        try:
            failed("permission", document.build(ctx, only={"trust"}))
        finally:
            trust_path.chmod(0o644)

    # 3b/4. Permission and I/O errors injected at Path.read_text for the
    # trust path only, through the real Context.read_text.
    for label, error in (
        ("permission_injected", PermissionError(errno.EACCES, "Permission denied")),
        ("io_error", OSError(errno.EIO, "Input/output error")),
        ("is_directory", IsADirectoryError(errno.EISDIR, "Is a directory")),
    ):
        ctx = world.build(trust=2)

        def fake(self, *args, _error=error, _target=ctx.config.gpu_handoff_state,
                 _real=Path.read_text, **kwargs):
            if str(self) == str(_target):
                raise _error
            return _real(self, *args, **kwargs)

        with mock.patch.object(Path, "read_text", fake):
            built = document.build(ctx, only={"trust"})
        failed(label, built)

    # Malformed contents remain a failure, not absence.
    failed("malformed", document.build(world.build(trust="garbage"), only={"trust"}))

    # 5/6. Recovery: once the file is readable again the valid claim returns.
    ctx = world.build(trust=1)
    real = Path.read_text
    target = ctx.config.gpu_handoff_state

    def eio(self, *args, **kwargs):
        if str(self) == str(target):
            raise OSError(errno.EIO, "Input/output error")
        return real(self, *args, **kwargs)

    with mock.patch.object(Path, "read_text", eio):
        failed("before_recovery", document.build(ctx, only={"trust"}))
    ctx.cache.clear()
    recovered = waybar_field(document.build(ctx, only={"trust"}), "trust")
    equals("recovered_known", recovered["known"], True)
    equals("recovered_identity", recovered["identity"], "dirty")
    equals("recovered_level", recovered["level"], 1)
