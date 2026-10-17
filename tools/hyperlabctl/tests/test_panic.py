"""hyperlabctl panic: cut and pause every running domain, restore exactly that."""

import io
import json
import os
import stat
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from harness import check, equals
from hyperlabctl.cli import main
from hyperlabctl.commands import panic
from hyperlabctl.config import Config, Context
from hyperlabctl.errors import ContractError, Unavailable
from hyperlabctl.runner import Result, Runner

VIRSH = ["/usr/bin/virsh", "-c", "qemu:///system", "-q"]


class FakeVirsh(Runner):
    """A small libvirt: domain states and live link states, nothing else.

    Any command this fake does not know fails, so an unexpected call (a
    destroy, a shutdown, a network command) can never pass silently.
    """

    def __init__(self, domains, fail=()):
        super().__init__()
        # name -> {"state": str, "links": {mac: [interface, "up"|"down"]}}
        self.domains = domains
        self.fail = set(fail)

    def run(self, argv, timeout=None):
        argv = [str(part) for part in argv]
        self.calls.append(tuple(argv))
        if argv[:4] != VIRSH:
            return Result(argv, 127, "", "not virsh")
        args = argv[4:]
        if tuple(args) in self.fail or (len(args) > 1 and (args[0], args[1]) in self.fail):
            return Result(argv, 1, "", "error: fixture failure for %s" % " ".join(args))
        verb = args[0]
        if args == ["list", "--state-running", "--name"]:
            names = [name for name, domain in self.domains.items() if domain["state"] == "running"]
            return Result(argv, 0, "".join(name + "\n" for name in names))
        domain = self.domains.get(args[1]) if len(args) > 1 else None
        if domain is None:
            return Result(argv, 1, "", "error: failed to get domain")
        if verb == "domstate":
            return Result(argv, 0, domain["state"] + "\n")
        if verb == "domiflist":
            rows = "".join(" %s   network   lab   virtio   %s\n" % (interface, mac)
                           for mac, (interface, _) in domain["links"].items())
            return Result(argv, 0, rows)
        if verb == "domif-getlink":
            interface, state = domain["links"][args[2]]
            return Result(argv, 0, "%s %s\n" % (args[2], state))
        if verb == "domif-setlink" and args[3] in ("up", "down"):
            if domain["state"] not in ("running", "paused"):
                return Result(argv, 1, "", "error: domain is not running")
            domain["links"][args[2]][1] = args[3]
            return Result(argv, 0, "Device updated successfully\n")
        if verb == "suspend" and domain["state"] == "running":
            domain["state"] = "paused"
            return Result(argv, 0, "Domain suspended\n")
        if verb == "resume" and domain["state"] == "paused":
            domain["state"] = "running"
            return Result(argv, 0, "Domain resumed\n")
        return Result(argv, 1, "", "error: unexpected %s" % " ".join(args))


def _world():
    domains = {
        "dev-01": {"state": "running", "links": {
            "52:54:00:00:00:01": ["vnet0", "up"], "52:54:00:00:00:02": ["vnet1", "up"]}},
        "win-01": {"state": "running", "links": {"52:54:00:00:00:03": ["vnet2", "up"]}},
        # Paused by the operator before the emergency stop.
        "held-01": {"state": "paused", "links": {"52:54:00:00:00:04": ["vnet3", "up"]}},
        "off-01": {"state": "shut off", "links": {"52:54:00:00:00:05": ["-", "up"]}},
    }
    return domains


def _ctx(runner, runtime):
    config = Config(repo_root=runtime, read_files=False,
                    overrides={"virsh_bin": "/usr/bin/virsh", "libvirt_uri": "qemu:///system"})
    return Context(config, runner, environ={"XDG_RUNTIME_DIR": str(runtime)})


def _runtime():
    runtime = Path(tempfile.mkdtemp(prefix="hyperlab-panic-"))
    os.chmod(runtime, 0o700)
    return runtime


def _cli(ctx, *argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(["--json", "panic", *argv], ctx=ctx)
    return code, json.loads(buffer.getvalue()) if buffer.getvalue().strip() else None


def _mutations(runner):
    return [call[4:] for call in runner.calls
            if call[4] in ("domif-setlink", "suspend", "resume")]


def test_panic_engage_cuts_then_pauses_every_running_domain():
    domains = _world()
    runner = FakeVirsh(domains)
    runtime = _runtime()
    code, payload = _cli(_ctx(runner, runtime), "engage")
    equals("panic_engage_exit", code, 0)
    equals("panic_engage_engaged", payload["engaged"], True)
    equals("panic_running_paused", (domains["dev-01"]["state"], domains["win-01"]["state"]),
           ("paused", "paused"))
    check("panic_links_down", all(link[1] == "down" for name in ("dev-01", "win-01")
                                  for link in domains[name]["links"].values()))
    record = payload["record"]["domains"]
    equals("panic_record_domains", sorted(record), ["dev-01", "win-01"])
    equals("panic_record_links", [link["mac"] for link in record["dev-01"]["links_down"]],
           ["52:54:00:00:00:01", "52:54:00:00:00:02"])
    check("panic_record_paused", record["dev-01"]["paused"] and record["win-01"]["paused"])
    # Fail-safe order: every link of a domain goes down before it is paused.
    order = _mutations(runner)
    for name in ("dev-01", "win-01"):
        downs = [i for i, call in enumerate(order) if call[:2] == ("domif-setlink", name)]
        pause = order.index(("suspend", name))
        check("panic_%s_links_before_pause" % name, downs and max(downs) < pause)


def test_panic_engage_never_touches_domains_that_were_not_running():
    domains = _world()
    runner = FakeVirsh(domains)
    runtime = _runtime()
    _cli(_ctx(runner, runtime), "engage")
    touched = {call[1] for call in _mutations(runner)} | {
        call[5] for call in runner.calls if len(call) > 5 and call[4] in ("domiflist", "domif-getlink")}
    check("panic_shut_off_untouched", "off-01" not in touched)
    check("panic_operator_paused_untouched", "held-01" not in touched)
    equals("panic_shut_off_state", domains["off-01"]["state"], "shut off")
    equals("panic_held_link", domains["held-01"]["links"]["52:54:00:00:00:04"][1], "up")
    verbs = {call[4] for call in runner.calls}
    check("panic_only_reversible_verbs",
          verbs <= {"list", "domiflist", "domif-getlink", "domif-setlink", "suspend"},
          "unexpected verbs %r" % verbs)


def test_panic_engage_continues_past_a_failing_domain_and_exits_non_zero():
    domains = _world()
    runner = FakeVirsh(domains, fail={("domif-setlink", "dev-01", "52:54:00:00:00:02", "down"),
                                      ("suspend", "win-01")})
    runtime = _runtime()
    code, payload = _cli(_ctx(runner, runtime), "engage")
    equals("panic_failure_exit", code, 1)
    equals("panic_failure_count", len(payload["failures"]), 2)
    check("panic_failure_names_link", any("dev-01" in f and "vnet1" in f for f in payload["failures"]))
    check("panic_failure_names_pause", any("win-01" in f and "paused" in f for f in payload["failures"]))
    # dev-01 is still paused after one of its links failed; win-01's link is
    # down even though it could not be paused.
    equals("panic_failing_link_domain_paused", domains["dev-01"]["state"], "paused")
    equals("panic_unpaused_domain_link_down", domains["win-01"]["links"]["52:54:00:00:00:03"][1], "down")
    record = payload["record"]["domains"]
    equals("panic_record_only_successes", [link["mac"] for link in record["dev-01"]["links_down"]],
           ["52:54:00:00:00:01"])
    equals("panic_record_unpaused", record["win-01"]["paused"], False)


def test_panic_engage_with_no_inventory_fails_loudly():
    runner = FakeVirsh(_world(), fail={("list", "--state-running", "--name")})
    code, payload = _cli(_ctx(runner, _runtime()), "engage")
    equals("panic_no_inventory_exit", code, 1)
    check("panic_no_inventory_reason", "could not be listed" in payload["failures"][0])


def test_panic_second_engage_keeps_the_first_record():
    domains = _world()
    runner = FakeVirsh(domains)
    runtime = _runtime()
    ctx = _ctx(runner, runtime)
    _, first = _cli(ctx, "engage")
    # Between the two presses a new Machine started; the first ones are paused.
    domains["new-01"] = {"state": "running", "links": {"52:54:00:00:00:06": ["vnet4", "up"]}}
    code, second = _cli(ctx, "engage")
    equals("panic_second_engage_exit", code, 0)
    equals("panic_second_keeps_time", second["record"]["engaged_at"], first["record"]["engaged_at"])
    equals("panic_second_keeps_domains", sorted(second["record"]["domains"]),
           ["dev-01", "new-01", "win-01"])
    equals("panic_second_keeps_links", second["record"]["domains"]["dev-01"],
           first["record"]["domains"]["dev-01"])


def test_panic_restore_undoes_exactly_what_engage_changed():
    domains = _world()
    domains["dev-01"]["links"]["52:54:00:00:00:02"][1] = "down"  # set down by the operator
    runner = FakeVirsh(domains)
    runtime = _runtime()
    ctx = _ctx(runner, runtime)
    _cli(ctx, "engage")
    code, payload = _cli(ctx, "restore", "--confirm")
    equals("panic_restore_exit", code, 0)
    equals("panic_restore_disengaged", payload["engaged"], False)
    equals("panic_restored_states", {name: domain["state"] for name, domain in domains.items()},
           {"dev-01": "running", "win-01": "running", "held-01": "paused", "off-01": "shut off"})
    equals("panic_restored_links", {mac: link[1] for domain in domains.values()
                                    for mac, link in domain["links"].items()},
           {"52:54:00:00:00:01": "up", "52:54:00:00:00:02": "down", "52:54:00:00:00:03": "up",
            "52:54:00:00:00:04": "up", "52:54:00:00:00:05": "up"})
    check("panic_restore_record_removed", not panic.record_path(ctx.environ).exists())
    # Links come up before the domain resumes.
    order = _mutations(runner)
    ups = [i for i, call in enumerate(order) if call[:2] == ("domif-setlink", "dev-01") and call[3] == "up"]
    check("panic_restore_links_before_resume", ups and max(ups) < order.index(("resume", "dev-01")))


def test_panic_restore_resumes_only_what_the_stop_paused():
    # win-01 could not be paused by the stop, only cut; the operator paused
    # it afterwards. Restore reconnects it and leaves it paused.
    domains = _world()
    runner = FakeVirsh(domains, fail={("suspend", "win-01")})
    runtime = _runtime()
    ctx = _ctx(runner, runtime)
    _cli(ctx, "engage")
    runner.fail = set()
    domains["win-01"]["state"] = "paused"
    code, _ = _cli(ctx, "restore", "--confirm")
    equals("panic_unpaused_restore_exit", code, 0)
    equals("panic_unpaused_stays_paused", domains["win-01"]["state"], "paused")
    equals("panic_unpaused_link_up", domains["win-01"]["links"]["52:54:00:00:00:03"][1], "up")
    check("panic_unpaused_not_resumed", ("resume", "win-01") not in _mutations(runner))


def test_panic_restore_keeps_what_it_could_not_restore():
    domains = _world()
    runner = FakeVirsh(domains)
    runtime = _runtime()
    ctx = _ctx(runner, runtime)
    _cli(ctx, "engage")
    runner.fail = {("resume", "win-01")}
    domains["dev-01"]["state"] = "shut off"  # shut down during the stop
    code, payload = _cli(ctx, "restore", "--confirm")
    equals("panic_partial_restore_exit", code, 1)
    equals("panic_partial_restore_left", sorted(payload["record"]["domains"]), ["win-01"])
    check("panic_partial_restore_note", any("dev-01" in note for note in payload["notes"]))
    runner.fail = set()
    code, payload = _cli(ctx, "restore", "--confirm")
    equals("panic_retry_restore_exit", code, 0)
    equals("panic_retry_restore_state", domains["win-01"]["state"], "running")
    equals("panic_retry_disengaged", payload["engaged"], False)


def test_panic_restore_keeps_a_domain_whose_state_cannot_be_read():
    domains = _world()
    runner = FakeVirsh(domains)
    runtime = _runtime()
    ctx = _ctx(runner, runtime)
    _cli(ctx, "engage")
    runner.fail = {("domstate", "dev-01")}
    runner.calls.clear()

    code, payload = _cli(ctx, "restore", "--confirm")
    equals("panic_unknown_state_exit", code, 1)
    if code != 1:
        return
    equals("panic_unknown_state_record", sorted(payload["record"]["domains"]), ["dev-01"])
    check("panic_unknown_state_reported", any("dev-01" in failure and "state" in failure
                                            for failure in payload["failures"]))
    check("panic_unknown_state_untouched", all(call[1] != "dev-01" for call in _mutations(runner)))
    equals("panic_unknown_state_stays_paused", domains["dev-01"]["state"], "paused")
    check("panic_unknown_state_record_on_disk", panic.read_record(ctx.environ)["domains"]["dev-01"]["paused"])

    runner.fail.clear()
    code, payload = _cli(ctx, "restore", "--confirm")
    equals("panic_unknown_state_retry_exit", code, 0)
    equals("panic_unknown_state_retry_resumed", domains["dev-01"]["state"], "running")
    check("panic_unknown_state_retry_reconnected", all(link[1] == "up"
                                                      for link in domains["dev-01"]["links"].values()))
    equals("panic_unknown_state_retry_disengaged", payload["engaged"], False)


def test_panic_restore_keeps_unconfirmed_inactive_states():
    for state in ("unknown", "in shutdown", "pmsuspended"):
        domains = _world()
        runner = FakeVirsh(domains)
        ctx = _ctx(runner, _runtime())
        _cli(ctx, "engage")
        domains["dev-01"]["state"] = state
        runner.calls.clear()

        code, payload = _cli(ctx, "restore", "--confirm")
        equals("panic_%s_state_exit" % state, code, 1)
        if code != 1:
            continue
        equals("panic_%s_state_retained" % state, sorted(payload["record"]["domains"]), ["dev-01"])
        check("panic_%s_state_untouched" % state, all(call[1] != "dev-01" for call in _mutations(runner)))
        domains["dev-01"]["state"] = "paused"
        code, payload = _cli(ctx, "restore", "--confirm")
        equals("panic_%s_state_retry" % state, (code, payload["engaged"]), (0, False))


def test_panic_restore_without_confirm_is_refused():
    domains = _world()
    runner = FakeVirsh(domains)
    runtime = _runtime()
    ctx = _ctx(runner, runtime)
    _cli(ctx, "engage")
    before = len(runner.calls)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(["panic", "restore"], ctx=ctx)
    equals("panic_unconfirmed_exit", code, 2)
    equals("panic_unconfirmed_no_calls", len(runner.calls), before)
    equals("panic_unconfirmed_still_paused", domains["dev-01"]["state"], "paused")
    try:
        panic.restore(ctx, ctx.environ, confirm=False)
    except ContractError:
        check("panic_unconfirmed_raises", True)
    else:
        check("panic_unconfirmed_raises", False)


def test_panic_record_is_private():
    runtime = _runtime()
    ctx = _ctx(FakeVirsh(_world()), runtime)
    _cli(ctx, "engage")
    directory = runtime / "hyperlab"
    path = directory / "panic.json"
    equals("panic_dir_mode", stat.S_IMODE(directory.stat().st_mode), 0o700)
    equals("panic_file_mode", stat.S_IMODE(path.stat().st_mode), 0o600)
    code, payload = _cli(ctx, "status")
    equals("panic_status_exit", code, 0)
    equals("panic_status_engaged", payload["engaged"], True)
    path.chmod(0o644)
    try:
        panic.read_record(ctx.environ)
    except Unavailable:
        check("panic_world_readable_refused", True)
    else:
        check("panic_world_readable_refused", False)
    path.chmod(0o600)
    path.write_text('{"schema": 1}')
    try:
        panic.read_record(ctx.environ)
    except Unavailable:
        check("panic_malformed_refused", True)
    else:
        check("panic_malformed_refused", False)
    path.unlink()
    path.symlink_to(runtime / "elsewhere.json")
    try:
        panic.read_record(ctx.environ)
    except Unavailable:
        check("panic_symlink_refused", True)
    else:
        check("panic_symlink_refused", False)


def test_panic_status_without_a_record_is_clear():
    code, payload = _cli(_ctx(FakeVirsh(_world()), _runtime()), "status")
    equals("panic_clear_exit", code, 0)
    equals("panic_clear", (payload["engaged"], payload["record"]), (False, None))


def test_panic_engage_with_nothing_running_does_nothing_to_domains():
    domains = {"off-01": {"state": "shut off", "links": {"52:54:00:00:00:05": ["-", "up"]}}}
    runner = FakeVirsh(domains)
    code, payload = _cli(_ctx(runner, _runtime()), "engage")
    equals("panic_idle_exit", code, 0)
    equals("panic_idle_domains", payload["record"]["domains"], {})
    equals("panic_idle_calls", [call[4] for call in runner.calls], ["list"])


def test_panic_engage_stops_even_when_its_record_is_unusable():
    # problems/emergency-stop-blocked-by-its-record.md
    for case in ("malformed", "unwritable"):
        domains = _world()
        runner = FakeVirsh(domains)
        runtime = _runtime()
        directory = runtime / "hyperlab"
        directory.mkdir(mode=0o700)
        path = directory / "panic.json"
        if case == "malformed":
            path.write_text("{not json")
            path.chmod(0o600)
            before = path.read_text()
        else:
            directory.chmod(0o500)
        try:
            code, payload = _cli(_ctx(runner, runtime), "engage")
        finally:
            directory.chmod(0o700)
        equals("panic_%s_exit" % case, code, 1)
        equals("panic_%s_still_paused" % case, (domains["dev-01"]["state"], domains["win-01"]["state"]),
               ("paused", "paused"))
        check("panic_%s_still_cut" % case, all(link[1] == "down" for name in ("dev-01", "win-01")
                                               for link in domains[name]["links"].values()))
        check("panic_%s_reported" % case, any("resume by hand" in item for item in payload["failures"]))
        if case == "malformed":
            equals("panic_malformed_left_alone", path.read_text(), before)
