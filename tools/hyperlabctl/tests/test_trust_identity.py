"""Network trust identity and the GPU trust gate are separate authorities."""

import world
from harness import check, equals
from hyperlabctl import document

LEGACY = "https://github.com/importriri/privatestack-ansible/hyperlab/1"


def _domains(domains):
    built = document.build(world.build(domains=domains, trust=None))
    return {row["name"]: row for row in built["domains"]}, built["problems"]


def _ids(problems):
    return [problem["id"] for problem in problems]


def test_managed_non_vfio_guest_takes_its_network_identity():
    rows, problems = _domains([{"name": "arch-dev", "state": "shut off", "memory_mb": 1024,
                                "network": "dev", "metadata": world.managed_metadata("dev")}])
    equals("arch_dev_identity", rows["arch-dev"]["trust_profile"], "dev")
    equals("arch_dev_source", rows["arch-dev"]["trust_source"], "network-profile")
    # It needs no GPU entry, and not having one is not a problem.
    equals("arch_dev_no_gpu_gate", rows["arch-dev"]["gpu_trust_profile"], None)
    check("arch_dev_no_problem", not any(p.startswith("domains.") for p in _ids(problems)))


def test_legacy_metadata_namespace_is_still_an_identity():
    rows, _ = _domains([{"name": "arch-dev", "state": "shut off", "memory_mb": 1024,
                         "network": "dev",
                         "metadata": world.managed_metadata("dev", namespace=LEGACY)}])
    equals("legacy_identity", rows["arch-dev"]["trust_profile"], "dev")


def test_vfio_guest_remains_guarded_by_gpu_domain_profiles():
    rows, problems = _domains([{"name": "arch-dev-vfio", "state": "running",
                                "memory_mb": 1024, "vfio": True, "network": "dev",
                                "metadata": world.managed_metadata("dev", "vfio")}])
    # A network identity does not substitute for the GPU gate.
    check("unguarded_vfio_still_flagged", "domains.unguarded_vfio" in _ids(problems))
    equals("unguarded_gate_absent", rows["arch-dev-vfio"]["gpu_trust_profile"], None)


def test_vfio_guest_whose_authorities_agree_is_classified():
    rows, problems = _domains([{"name": "win11clean-valley", "state": "running",
                                "memory_mb": 1024, "vfio": True, "network": "clean",
                                "metadata": world.managed_metadata("clean", "vfio")}])
    equals("agreed_identity", rows["win11clean-valley"]["trust_profile"], "clean")
    equals("agreed_gate", rows["win11clean-valley"]["gpu_trust_profile"], "clean")
    check("agreed_no_problem", not any(p.startswith("domains.") for p in _ids(problems)))


def test_managed_network_identity_is_independent_from_gpu_handoff_profile():
    rows, problems = _domains([{"name": "win11clean-valley", "state": "running",
                                "memory_mb": 1024, "vfio": True, "network": "dirty",
                                "metadata": world.managed_metadata("dirty", "vfio")}])
    equals("split_identity", rows["win11clean-valley"]["trust_profile"], "dirty")
    equals("split_source", rows["win11clean-valley"]["trust_source"], "network-profile")
    equals("split_gpu_gate", rows["win11clean-valley"]["gpu_trust_profile"], "clean")
    check("split_no_conflict", "domains.trust_conflict" not in _ids(problems))


def test_metadata_that_disagrees_with_attached_network_invents_nothing():
    rows, problems = _domains([{"name": "arch-dev", "state": "shut off", "memory_mb": 1024,
                                "network": "clean", "metadata": world.managed_metadata("dev")}])
    equals("mismatch_identity", rows["arch-dev"]["trust_profile"], None)
    check("mismatch_flagged", "domains.network_identity_mismatch" in _ids(problems))


def test_undeclared_network_profile_is_not_an_identity():
    rows, _ = _domains([{"name": "odd", "state": "shut off", "memory_mb": 1024,
                         "network": "wild", "metadata": world.managed_metadata("wild")}])
    equals("undeclared_identity", rows["odd"]["trust_profile"], None)


def test_unmanaged_domain_on_a_trust_network_is_not_classified_by_it():
    rows, _ = _domains([{"name": "external", "state": "running", "memory_mb": 1024,
                         "network": "dev"}])
    equals("unmanaged_identity", rows["external"]["trust_profile"], None)
    equals("unmanaged_managed", rows["external"]["managed"], False)


def test_unmanaged_gpu_gated_domain_keeps_its_gate_identity():
    rows, _ = _domains([{"name": "win11clean-valley", "state": "shut off",
                         "memory_mb": 1024, "vfio": True, "network": "clean"}])
    equals("gated_identity", rows["win11clean-valley"]["trust_profile"], "clean")
    equals("gated_source", rows["win11clean-valley"]["trust_source"], "gpu-domain-profile")


def test_unreadable_domain_never_invents_trust():
    ctx = world.build(domains=[{"name": "arch-dev", "state": "running", "memory_mb": 1024,
                                "network": "dev", "metadata": world.managed_metadata("dev")}])
    virsh = ["/usr/bin/virsh", "-c", "qemu:///system", "-q"]
    ctx.runner.register(virsh + ["dumpxml", "arch-dev"], (1, ""))
    rows = {row["name"]: row for row in document.build(ctx)["domains"]}
    equals("unreadable_identity", rows["arch-dev"]["trust_profile"], None)
