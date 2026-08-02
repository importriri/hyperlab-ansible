import world
from harness import check, equals
from hyperlabctl import document
from hyperlabctl.providers.memory import budget

RUNNING_VFIO = [{"name": "win11clean-valley", "state": "running",
                 "memory_mb": 6144, "vfio": True}]


def test_memory_budget_subtracts_reservations_and_overheads():
    ctx = world.build(domains=RUNNING_VFIO, trust=3)
    result = budget(ctx)
    equals("total_mb", result["total_mb"], 7761)
    equals("committed_mb", result["committed_mb"], 6144)
    equals("overhead_mb", result["overhead_mb"], 768)
    equals("assignable_mb", result["assignable_mb"], 0)
    check("negative_flag_set", result["negative"] is True)


def test_memory_budget_on_an_idle_host_leaves_the_reserve():
    result = budget(world.build(domains=[], trust=None))
    equals("idle_assignable", result["assignable_mb"], 7761 - 2048)
    check("idle_not_negative", result["negative"] is False)


def test_stopped_domain_reports_how_much_it_is_short():
    domains = RUNNING_VFIO + [{"name": "fedora-dev", "state": "shut off",
                               "memory_mb": 4096, "network": "dev"}]
    built = document.build(world.build(domains=domains, trust=3))
    fedora = [d for d in built["domains"] if d["name"] == "fedora-dev"][0]
    equals("blocked_reason", fedora["blocked"]["reason"], "memory")
    equals("blocked_short_mb", fedora["blocked"]["short_mb"], 4096)


def test_running_domain_is_never_blocked():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    win = [d for d in built["domains"] if d["name"] == "win11clean-valley"][0]
    equals("running_not_blocked", win["blocked"], None)
    equals("running_marked_vfio", win["vfio"], True)
    equals("running_network", win["network"], "clean")


def test_gpu_bound_to_vfio_is_reported_as_bound():
    built = document.build(world.build(domains=RUNNING_VFIO, trust=3))
    equals("gpu_bound", built["gpu"]["bound"], True)
    equals("gpu_driver", built["gpu"]["driver"], "vfio-pci")
    equals("gpu_held_by", built["gpu"]["held_by"], "win11clean-valley")


def test_gpu_on_nouveau_is_reported_as_not_bound():
    ctx = world.build(drivers={"0000:01:00.0": "nouveau",
                               "0000:01:00.1": "snd_hda_intel"}, trust=None)
    built = document.build(ctx)
    equals("gpu_not_bound", built["gpu"]["bound"], False)
    check("gpu_problem_raised",
          any(p["id"] == "gpu.not_bound" for p in built["problems"]))


def test_gpu_half_bound_is_not_bound():
    """The state seen on the Nitro: VGA on vfio-pci, audio still on
    snd_hda_intel. Both functions must move or the passthrough is not ready."""
    ctx = world.build(drivers={"0000:01:00.0": "vfio-pci",
                               "0000:01:00.1": "snd_hda_intel"}, trust=None)
    built = document.build(ctx)
    equals("half_bound_not_bound", built["gpu"]["bound"], False)
    equals("half_bound_driver_ambiguous", built["gpu"]["driver"], None)
    equals("half_bound_drivers_listed", built["gpu"]["drivers"],
           ["snd_hda_intel", "vfio-pci"])
    check("half_bound_problem_raised",
          any(p["id"] == "gpu.not_bound" for p in built["problems"]))


def test_gpu_with_no_owner_reports_none():
    built = document.build(world.build(domains=[], trust=None))
    equals("gpu_free", built["gpu"]["held_by"], None)


def test_trust_absent_state_file_means_unclaimed():
    built = document.build(world.build(trust=None))
    equals("unclaimed_level", built["trust"]["level"], None)
    equals("unclaimed_can_ascend", built["trust"]["can_ascend"], True)


def test_trust_claimed_level_maps_to_a_domain_name():
    built = document.build(world.build(trust=0))
    equals("claimed_name", built["trust"]["name"], "lab")
    equals("claimed_can_ascend", built["trust"]["can_ascend"], False)


def test_trust_level_outside_the_ladder_is_an_error():
    built = document.build(world.build(trust=9))
    check("unmapped_trust_is_error",
          any(p["id"] == "trust.level_unmapped" and p["severity"] == "error"
              for p in built["problems"]))


def test_inactive_network_is_named_not_just_counted():
    built = document.build(world.build(trust=None, networks_active=["clean", "dev"]))
    equals("active_count", built["networks"]["active"], 2)
    equals("inactive_named", built["networks"]["inactive"], ["dirty", "lab", "services"])


def test_vfio_domain_outside_gpu_domain_profiles_is_flagged():
    domains = [{"name": "rogue-vfio", "state": "running", "memory_mb": 2048, "vfio": True}]
    built = document.build(world.build(domains=domains, trust=None))
    check("unguarded_vfio_flagged",
          any(p["id"] == "domains.unguarded_vfio" for p in built["problems"]))
