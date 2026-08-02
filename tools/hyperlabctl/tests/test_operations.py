"""The CLI and the panel share one refusal. This is where that is pinned."""

import world
from harness import check, equals
from hyperlabctl import operations

RUNNING_VFIO = [{"name": "win11clean-valley", "state": "running",
                 "memory_mb": 6144, "vfio": True}]
BLOCKED = RUNNING_VFIO + [{"name": "fedora-dev", "state": "shut off",
                           "memory_mb": 4096, "network": "dev"}]


def test_start_refuses_and_names_the_shortfall():
    ctx = world.build(domains=BLOCKED, trust=3)
    outcome = operations.start(ctx, "fedora-dev")
    equals("refused", outcome.ok, False)
    equals("did_not_act", outcome.acted, False)
    check("shortfall_named", "short 4096" in outcome.message)


def test_start_never_reaches_virsh_when_refused():
    ctx = world.build(domains=BLOCKED, trust=3)
    operations.start(ctx, "fedora-dev")
    check("virsh_start_absent",
          not any(call[-2:] == ("start", "fedora-dev") for call in ctx.runner.calls))


def test_start_on_a_running_domain_is_a_noop_that_still_succeeds():
    ctx = world.build(domains=RUNNING_VFIO, trust=3)
    outcome = operations.start(ctx, "win11clean-valley")
    equals("noop_ok", outcome.ok, True)
    equals("noop_did_not_act", outcome.acted, False)


def test_stop_on_a_running_domain_calls_shutdown_not_destroy():
    ctx = world.build(domains=RUNNING_VFIO, trust=3)
    outcome = operations.stop(ctx, "win11clean-valley")
    equals("stop_ok", outcome.ok, True)
    check("shutdown_called",
          any(call[-2:] == ("shutdown", "win11clean-valley") for call in ctx.runner.calls))
    check("destroy_never_called",
          not any("destroy" in call for call in ctx.runner.calls))


def test_the_panel_and_the_cli_refuse_with_the_same_message():
    import io
    from contextlib import redirect_stdout
    from hyperlabctl.cli import main
    ctx = world.build(domains=BLOCKED, trust=3)
    direct = operations.start(ctx, "fedora-dev").message
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["vm", "start", "fedora-dev"], ctx=world.build(domains=BLOCKED, trust=3))
    equals("same_refusal", buffer.getvalue().strip(), direct)


SIGNAL = ("/usr/bin/pkill", "-RTMIN+8", "-x", "waybar")


def test_a_successful_start_signals_the_bar():
    ctx = world.build(domains=[{"name": "debian-dev", "state": "shut off",
                                "memory_mb": 1024, "network": "dev"}], trust=None)
    operations.start(ctx, "debian-dev")
    check("bar_signalled_after_start", SIGNAL in ctx.runner.calls)


def test_a_refused_start_does_not_signal_the_bar():
    ctx = world.build(domains=BLOCKED, trust=3)
    operations.start(ctx, "fedora-dev")
    check("bar_not_signalled_after_refusal", SIGNAL not in ctx.runner.calls)


def test_a_missing_pkill_does_not_fail_the_operation():
    """RecordedRunner returns 127 for anything unregistered, which is exactly
    what a host without pkill or without waybar looks like."""
    ctx = world.build(domains=[{"name": "debian-dev", "state": "shut off",
                                "memory_mb": 1024, "network": "dev"}], trust=None)
    outcome = operations.start(ctx, "debian-dev")
    equals("start_still_succeeded", outcome.ok, True)


def test_start_refuses_when_the_memory_budget_cannot_be_read():
    ctx = world.build(domains=[{"name": "debian-dev", "state": "shut off",
                                "memory_mb": 1024, "network": "dev"}],
                      trust=None, profile_report=False)
    outcome = operations.start(ctx, "debian-dev")
    equals("missing_budget_refused", outcome.ok, False)
    check("missing_budget_never_started",
          not any(call[-2:] == ("start", "debian-dev") for call in ctx.runner.calls))


def test_managed_domain_cannot_bypass_the_m3_start_playbook():
    ctx = world.build(domains=[{"name": "debian-dev", "state": "shut off",
                                "memory_mb": 1024, "network": "dev"}], trust=None)
    argv = ["/usr/bin/virsh", "-c", "qemu:///system", "-q", "dumpxml", "debian-dev"]
    ctx.runner.register(argv, """<domain type='kvm'>
      <name>debian-dev</name><memory unit='MiB'>1024</memory>
      <metadata><hyperlab:instance xmlns:hyperlab='https://github.com/importriri/privatestack-ansible/hyperlab/1'
        schema='1' lifecycle='permanent' device-profile='standard'/></metadata>
      <devices><interface type='network'><source network='dev'/></interface></devices>
    </domain>""")
    outcome = operations.start(ctx, "debian-dev")
    equals("managed_direct_start_refused", outcome.ok, False)
    check("managed_direct_start_names_m3", "M3 lifecycle playbook" in outcome.message)
    check("managed_direct_start_never_called",
          not any(call[-2:] == ("start", "debian-dev") for call in ctx.runner.calls))


def test_unguarded_vfio_domain_cannot_start_from_the_cockpit():
    ctx = world.build(domains=[{"name": "rogue-vfio", "state": "shut off",
                                "memory_mb": 1024, "vfio": True}], trust=None)
    outcome = operations.start(ctx, "rogue-vfio")
    equals("unguarded_vfio_start_refused", outcome.ok, False)
    check("unguarded_vfio_start_never_called",
          not any(call[-2:] == ("start", "rogue-vfio") for call in ctx.runner.calls))
