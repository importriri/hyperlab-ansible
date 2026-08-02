"""End to end through argparse, with the fake host injected."""

import io
import json
from contextlib import redirect_stdout

import world
from harness import check, equals
from hyperlabctl.cli import main

RUNNING_VFIO = [{"name": "win11clean-valley", "state": "running",
                 "memory_mb": 6144, "vfio": True}]


def _run(argv, ctx):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv, ctx=ctx)
    return code, buffer.getvalue()


WITHIN_BUDGET = [{"name": "debian-dev", "state": "running",
                  "memory_mb": 2048, "network": "dev"}]


def test_status_json_parses_and_carries_the_schema_version():
    code, output = _run(["--json", "status"], world.build(domains=WITHIN_BUDGET, trust=None))
    parsed = json.loads(output)
    equals("status_schema_version", parsed["schema_version"], 1)
    equals("status_exit_code_ok", code, 0)


def test_the_real_nitro_win11_allocation_is_reported_as_over_budget():
    """6 GB of VFIO guest on 8 GB of Nitro does not fit, and this says so
    before the OOM killer does."""
    code, output = _run(["--json", "status"], world.build(domains=RUNNING_VFIO, trust=3))
    parsed = json.loads(output)
    equals("nitro_status_exit", code, 2)
    check("nitro_overcommit_flagged",
          any(problem["id"] == "memory.overcommitted" for problem in parsed["problems"]))


def test_status_exits_two_when_a_problem_is_an_error():
    ctx = world.build(domains=[{"name": "rogue-vfio", "state": "running",
                                "memory_mb": 2048, "vfio": True}], trust=None)
    code, _ = _run(["--json", "status"], ctx)
    equals("status_exit_code_error", code, 2)


def test_waybar_command_emits_parseable_json():
    _, output = _run(["waybar"], world.build(domains=RUNNING_VFIO, trust=3))
    payload = json.loads(output.strip())
    equals("waybar_cli_text", payload["text"], "clean 3")


def test_actions_json_matches_the_registry_length():
    from hyperlabctl import registry
    _, output = _run(["--json", "actions"], world.build(trust=None))
    equals("actions_count", len(json.loads(output)), len(registry.actions()))


def test_vm_list_names_every_domain():
    ctx = world.build(domains=RUNNING_VFIO + [{"name": "debian-dev", "state": "shut off",
                                               "memory_mb": 2048, "network": "dev"}], trust=3)
    _, output = _run(["vm", "list"], ctx)
    check("list_has_win11", "win11clean-valley" in output)
    check("list_has_debian", "debian-dev" in output)


def test_vm_start_is_refused_when_the_budget_cannot_hold_it():
    ctx = world.build(domains=RUNNING_VFIO + [{"name": "fedora-dev", "state": "shut off",
                                               "memory_mb": 4096, "network": "dev"}], trust=3)
    code, output = _run(["vm", "start", "fedora-dev"], ctx)
    equals("refused_exit_code", code, 2)
    check("refusal_states_the_shortfall", "short 4096" in output)
    check("virsh_start_never_called",
          ("/usr/bin/virsh", "-c", "qemu:///system", "-q", "start", "fedora-dev")
          not in ctx.runner.calls)


def test_vm_start_proceeds_when_the_budget_allows_it():
    ctx = world.build(domains=[{"name": "debian-dev", "state": "shut off",
                                "memory_mb": 2048, "network": "dev"}], trust=None)
    code, _ = _run(["vm", "start", "debian-dev"], ctx)
    equals("start_exit_code", code, 0)
    check("virsh_start_called",
          ("/usr/bin/virsh", "-c", "qemu:///system", "-q", "start", "debian-dev")
          in ctx.runner.calls)


def test_vm_stop_on_a_stopped_domain_does_nothing():
    ctx = world.build(domains=[{"name": "debian-dev", "state": "shut off",
                                "memory_mb": 2048, "network": "dev"}], trust=None)
    code, output = _run(["vm", "stop", "debian-dev"], ctx)
    equals("stop_noop_exit", code, 0)
    check("stop_noop_message", "not running" in output)


def test_global_json_flag_is_accepted_after_the_subcommand():
    code, output = _run(["actions", "--json"], world.build(trust=None))
    equals("trailing_json_exit", code, 0)
    check("trailing_json_parses", isinstance(json.loads(output), list))


def test_vm_list_json_flag_is_accepted_in_shell_surface_order():
    code, output = _run(["vm", "list", "--json"], world.build(domains=WITHIN_BUDGET, trust=None))
    equals("vm_trailing_json_exit", code, 0)
    equals("vm_trailing_json_name", json.loads(output)[0]["name"], "debian-dev")
