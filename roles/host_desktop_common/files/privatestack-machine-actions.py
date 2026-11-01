#!/usr/bin/env python3
"""Typed machine-operation boundary for the HyperLab shell.

Machine capabilities and reviewed operations cross this boundary:

  capabilities NAME   what may be done to this machine right now, and why not
  VERB NAME           do exactly one reviewed operation to this machine

Both answers are derived from live state every time: the live libvirt
inventory, the checked HyperLab spec, the strict runtime SSH inventory and the
reviewed action registry. The shell never reconstructs these rules, and a
capability answer is advice for presentation only -- this bridge re-derives
everything before it acts.

Private diagnostics cross it as one bounded foreground request (ADR 0054):

  diagnostics NAME REQUEST   collect one private archive with a correlated result

The host clipboard crosses it as one more operation (ADR 0020):

  clipboard NAME     send the host clipboard text to this machine, once

The Workbench crosses it as two more (ADR 0015); its candidates are never
product Machines, and start, shutdown and console reach them as any domain:

  workbench          Golden Image candidates with their live state
  seal NAME          capture a shut-off candidate through the operation runner

A blocked USB device crosses it as two more (ADR 0038); a device is never a
Machine, and only one that presents no keyboard or mouse is allowed here:

  usb                           the host's USB devices, blocked ones first
  usb-allow PORT SCOPE DEVICE   allow the blocked device DEVICE (vendor:product)
                                at PORT, once or permanently

The emergency stop crosses it as two more (ADR 0047). Engaging it is a host
key, never this bridge; the shell only reads it and restores it:

  panic-status           whether an emergency stop is engaged, and on what
  panic-restore          reconnect and resume exactly what it changed (the
                         shell asks for a typed confirmation first)

Creation crosses it as two more questions (ADR 0017):

  create-plan                                   what may be created, within which limits
  create TEMPLATE NAME LIFECYCLE NETWORK PROFILE [MEMORY VCPUS DISK]
                                                record, project, then provision

Every response is one JSON object on stdout so the shell reads structure
instead of prose. Managed lifecycle reports correlated durable operation records, never spawn success.
"""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

HYPERLABCTL = "/usr/local/bin/hyperlabctl"
OPERATION = "/usr/local/bin/privatestack-operation"
CHECKOUT_POINTER = Path("/etc/hyperlabctl/checkout")
DIAGNOSTICS_OUTPUT = Path.home() / "hyperlab-evidence" / "diagnostics"
# Five host commands (5*30), inventory recovery (35), resolution (5),
# SSH readiness (up to 32), six guest commands (6*60), plus publication.
DIAGNOSTICS_TIMEOUT = 660

VERBS = (
    "start",
    "shutdown",
    "reboot",
    "console",
    "ssh",
    "looking-glass",
    "restart-capture",
    "force-stop",
    "diagnostics",
)

# Operations that hand the guest a signal it cannot negotiate. The shell
# confirms them and the registry enforces them; both layers apply.
DESTRUCTIVE_VERBS = ("force-stop",)

# Transports. Each one becomes the client process it opens, so the shell owns
# one runner per open connection and never serializes lifecycle behind them.
CONNECTION_VERBS = ("console", "ssh", "looking-glass")

# Actions that are launched in their own terminal and outlive this process.
DETACHED_PREFIXES = ("vm.managed-",)
DETACHED_ACTIONS = ("vm.force-stop",)

# libvirt states from which a start is meaningful. Anything else -- paused,
# in shutdown, pmsuspended, unknown -- is reported as such, never as
# "startable" by elimination.
STARTABLE_STATES = ("shut off", "crashed")


class Refused(RuntimeError):
    pass


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def cli_json(*args: str, timeout: int = 15) -> Any:
    result = subprocess.run(
        [HYPERLABCTL, "--json", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        raise Refused(
            result.stderr.strip()
            or result.stdout.strip()
            or "hyperlabctl request failed"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Refused("invalid hyperlabctl JSON") from exc


def live_machine(name: str) -> dict[str, Any]:
    rows = cli_json("vm", "list")
    if not isinstance(rows, list):
        raise Refused("invalid live machine inventory")

    matches = [
        row for row in rows
        if isinstance(row, dict) and row.get("name") == name
    ]
    if len(matches) != 1:
        raise Refused("machine is not uniquely present in live inventory")
    return matches[0]


def managed_spec(name: str) -> dict[str, Any] | None:
    rows = cli_json("compose", "list")
    if not isinstance(rows, list):
        raise Refused("invalid HyperLab spec inventory")

    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        spec = row.get("spec")
        if isinstance(spec, dict) and spec.get("name") == name:
            matches.append(row)

    if len(matches) > 1:
        raise Refused("machine maps to more than one HyperLab spec")

    return matches[0] if matches else None


def resolve(
    action_id: str,
    name: str,
    spec_row: dict[str, Any] | None,
) -> list[str]:
    args = ["actions", "--resolve", action_id]

    if action_id in {
        "vm.console",
        "vm.ssh",
        "vm.clipboard-send",
        "vm.looking-glass",
        "vm.looking-glass-health",
        "vm.looking-glass-restart",
        "vm.start",
        "vm.stop",
        "machine.diagnostics",
        "machine.diagnostics-host",
    }:
        args += ["--domain", name]
    else:
        if spec_row is None:
            raise Refused("managed action has no HyperLab spec")
        path = spec_row.get("path")
        if not isinstance(path, str) or not path:
            raise Refused("managed spec has no validated path")
        args += ["--spec", path, "--domain", name]

    argv = cli_json(*args)
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(part, str) and part for part in argv)
    ):
        raise Refused("registry returned an invalid command")
    return argv


def runtime_ssh_problem(name: str) -> str | None:
    """Mirror the reviewed open path's runtime SSH inventory policy.

    `hyperlabctl open ssh` (commands/open.py `_runtime_inventory`) requires a
    real runtime directory owned by this user, and a regular, non-symlink,
    user-owned, mode-0600 `<name>.ini` inside it. A missing file is not a
    refusal there: the open path publishes it from the managed spec. This
    answers the same question the same way, so the capability shown is the
    capability the open path will honour. Returns None when SSH may proceed.
    """
    runtime = Path(
        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    )
    try:
        info = runtime.lstat()
    except OSError:
        return "runtime directory is unavailable"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return "runtime directory is not a real directory"
    if info.st_uid != os.getuid():
        return "runtime directory is not owned by the current user"

    inventory = runtime / f"{name}.ini"
    try:
        info = inventory.lstat()
    except FileNotFoundError:
        # Published on demand by the open path from the managed spec.
        return None
    except OSError:
        return "cannot inspect runtime SSH inventory"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "runtime SSH inventory is not a regular file"
    if info.st_uid != os.getuid():
        return "runtime SSH inventory has the wrong owner"
    if stat.S_IMODE(info.st_mode) != 0o600:
        return "runtime SSH inventory has the wrong mode"
    return None


def managed_identity(
    machine: dict[str, Any],
    spec_row: dict[str, Any] | None,
) -> bool:
    """Whether this machine is HyperLab-managed, from both authorities.

    The live domain metadata and the checked spec inventory must agree. A
    managed domain whose spec cannot be found is not an external domain --
    offering it direct lifecycle would only be refused downstream -- and an
    unreadable domain is neither.
    """
    live = machine.get("managed")
    if live is not True and live is not False:
        raise Refused("managed status of this machine could not be read")
    if live and spec_row is None:
        raise Refused("this managed machine's HyperLab spec is unavailable")
    if not live and spec_row is not None:
        raise Refused("machine metadata and HyperLab spec disagree")
    return live


def choose_action(
    verb: str,
    name: str,
    machine: dict[str, Any],
    spec_row: dict[str, Any] | None,
) -> str:
    state = str(machine.get("state") or "unknown").lower()
    running = state == "running"

    if verb == "diagnostics":
        return diagnostics_action(name, machine, spec_row)

    if verb == "start":
        if running:
            raise Refused("machine is already running")
        if state not in STARTABLE_STATES:
            raise Refused("machine is %s, not shut off" % state)
        managed = managed_identity(machine, spec_row)
        return "vm.managed-start" if managed else "vm.start"

    if verb == "shutdown":
        if not running:
            raise Refused("machine is not running")
        managed = managed_identity(machine, spec_row)
        return "vm.managed-shutdown" if managed else "vm.stop"

    if verb == "reboot":
        if not running:
            raise Refused("reboot requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("reboot requires a running managed machine")
        return "vm.managed-reboot"

    if verb == "console":
        if not running:
            raise Refused("console requires a running machine")
        return "vm.console"

    if verb == "ssh":
        if not running:
            raise Refused("SSH requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("SSH requires a running managed machine")
        problem = runtime_ssh_problem(name)
        if problem is not None:
            raise Refused(problem)
        return "vm.ssh"

    if verb == "looking-glass":
        if not running:
            raise Refused("Looking Glass requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("Looking Glass requires a running managed machine")
        if machine.get("vfio") is not True:
            raise Refused("Looking Glass requires VFIO")

        spec = spec_row.get("spec")
        image = spec_row.get("image")
        if not isinstance(spec, dict) or not isinstance(image, dict):
            raise Refused("Looking Glass metadata is unavailable")
        if spec.get("looking_glass") is not True:
            raise Refused("Looking Glass is disabled by the machine spec")

        os_family = str(image.get("os_family") or "")
        mode = str(spec.get("looking_glass_mode") or "")
        if os_family != "windows" and mode != "linux-experimental":
            raise Refused("Looking Glass transport is not approved")

        return "vm.looking-glass"

    if verb == "restart-capture":
        # The stream of a Linux sender only (ADR 0045): the Windows sender is
        # not restarted from here.
        if not running:
            raise Refused("restarting the capture requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("restarting the capture requires a running managed machine")
        if machine.get("vfio") is not True:
            raise Refused("restarting the capture requires VFIO")
        spec = spec_row.get("spec")
        image = spec_row.get("image")
        if not isinstance(spec, dict) or not isinstance(image, dict):
            raise Refused("Looking Glass metadata is unavailable")
        if spec.get("looking_glass") is not True:
            raise Refused("Looking Glass is disabled by the machine spec")
        if (str(image.get("os_family") or "") != "linux"
                or str(spec.get("looking_glass_mode") or "") != "linux-experimental"):
            raise Refused("only a Linux Looking Glass capture can be restarted")
        return "vm.looking-glass-restart"

    if verb == "force-stop":
        if not running:
            raise Refused("force stop requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("force stop requires a running managed machine")
        if machine.get("vfio") is not True:
            raise Refused("force stop is restricted to managed VFIO guests")
        return "vm.force-stop"

    raise Refused("unsupported machine operation")


def diagnostics_action(
    name: str, machine: dict[str, Any], spec_row: dict[str, Any] | None,
) -> str:
    """Product membership, checked spec and current live identity must all agree."""
    if not MACHINE_ID.fullmatch(name) or not managed_identity(machine, spec_row):
        raise Refused("diagnostics require a registered product Machine")
    spec = spec_row.get("spec") if spec_row else None
    if not isinstance(spec, dict) or spec.get("name") != name or not isinstance(spec.get("image"), str):
        raise Refused("the checked Machine spec is unavailable")
    try:
        payload = cli_json("machine", "inventory")
    except (Refused, OSError, subprocess.TimeoutExpired):
        raise Refused("the product Machine inventory is unavailable") from None
    if (not isinstance(payload, dict) or payload.get("machines_available") is not True
            or payload.get("runtime_available") is not True
            or not isinstance(payload.get("machines"), list)):
        raise Refused("the product Machine inventory is unavailable")
    matches = [row for row in payload["machines"] if isinstance(row, dict) and row.get("name") == name]
    if len(matches) != 1:
        raise Refused("diagnostics require one uniquely registered product Machine")
    row = matches[0]
    if (row.get("product_managed") is not True or row.get("managed") is not True
            or row.get("runtime_present") is not True or row.get("runtime_drift") is not False
            or machine.get("product_managed") is not True):
        raise Refused("the Machine's managed runtime identity is unavailable or drifting")
    image = row.get("image")
    if (not isinstance(image, dict) or not isinstance(image.get("id"), str)
            or not isinstance(image.get("sha256"), str) or not SHA256.fullmatch(image["sha256"])):
        raise Refused("the Machine's registered image identity is unavailable")
    identity = {
        "image": image["id"], "lifecycle": row.get("lifecycle"),
        "device_profile": row.get("device_capability"), "network_profile": row.get("network_profile"),
        "gpu_handoff_profile": row.get("gpu_handoff_profile"),
    }
    if (identity["lifecycle"] not in ("permanent", "disposable")
            or identity["device_profile"] not in ("standard", "vfio")
            or not isinstance(identity["network_profile"], str)
            or any(spec.get(key) != value for key, value in identity.items())):
        raise Refused("the checked spec and product Machine identity disagree")
    live_identity = {**identity, "trust_profile": identity["network_profile"],
                     "image_sha256": image["sha256"]}
    del live_identity["network_profile"]
    if any(machine.get(key) != value for key, value in live_identity.items()):
        raise Refused("the live and registered Machine identity disagree")
    vfio = identity["device_profile"] == "vfio"
    if (machine.get("vfio") is not vfio
            or machine.get("gpu_policy_state") != ("verified" if vfio else "not-required")
            or (vfio and machine.get("gpu_trust_profile") != identity["gpu_handoff_profile"])):
        raise Refused("the live Machine device identity disagrees")
    state = machine.get("state")
    if state != row.get("state") or state not in ("running", "shut off"):
        raise Refused("diagnostics require a consistently running or shut-off Machine")
    return "machine.diagnostics" if state == "running" else "machine.diagnostics-host"


def diagnostics_directory() -> set[str]:
    """Refuse redirected output, including a redirected parent, before any collection."""
    directory = DIAGNOSTICS_OUTPUT
    for path in (*reversed(directory.parents), directory):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise Refused("the diagnostics directory is redirected or unavailable")
    if not directory.exists():
        return set()
    if directory.stat().st_uid != os.getuid():
        raise Refused("the diagnostics directory has the wrong owner")
    return {path.name for path in directory.iterdir()}


def diagnostics_result(payload: Any, name: str, request_id: str, scope: str,
                       previous: set[str]) -> dict[str, Any]:
    """Only newly published private archives and manifest counts reach the pane."""
    if (not isinstance(payload, dict) or payload.get("machine") != name
            or payload.get("scope") != scope
            or not isinstance(payload.get("collected_at"), str)
            or not re.fullmatch(r"[0-9]{8}T[0-9]{6}", payload["collected_at"])
            or not isinstance(payload.get("files"), dict) or not payload["files"]
            or not isinstance(payload.get("missing"), dict)
            or payload["files"].keys() & payload["missing"].keys()):
        raise Refused("invalid diagnostics result")
    for source, entry in payload["files"].items():
        if (not isinstance(source, str) or not isinstance(entry, dict)
                or any(type(entry.get(key)) is not int or entry[key] < 0 for key in ("bytes", "redactions"))
                or type(entry.get("truncated")) is not bool):
            raise Refused("invalid diagnostics counts")
    if any(not isinstance(error, str) for error in payload["missing"].values()):
        raise Refused("invalid unavailable diagnostics sources")
    for source in (*payload["files"], *payload["missing"]):
        if (not source.startswith(("host/", "guest/")) or ".." in Path(source).parts
                or (scope == "host-only" and not source.startswith("host/"))):
            raise Refused("invalid diagnostics scope")
    expected = DIAGNOSTICS_OUTPUT / f"{name}-{payload['collected_at']}.tar.gz"
    if payload.get("archive") != str(expected) or expected.name in previous:
        raise Refused("diagnostics did not publish a new archive")
    diagnostics_directory()
    if stat.S_IMODE(DIAGNOSTICS_OUTPUT.stat().st_mode) != 0o700:
        raise Refused("the diagnostics directory is not private")
    fd = os.open(expected, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size == 0
                or info.st_nlink != 1):
            raise Refused("the diagnostics archive is not a private regular file")
    finally:
        os.close(fd)
    return {"phase": "diagnostics", "request_id": request_id, "machine": name, "scope": scope,
            "archive": str(expected), "collected": len(payload["files"]),
            "unavailable": len(payload["missing"]),
            "redactions": sum(entry["redactions"] for entry in payload["files"].values())}


def unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Refused("duplicate diagnostics JSON field")
        result[key] = value
    return result


def collect_diagnostics(name: str, request_id: str) -> dict[str, Any]:
    if not MACHINE_ID.fullmatch(name) or not TOKEN.fullmatch(request_id):
        raise Refused("invalid diagnostics request")
    # Capabilities are advisory. Re-read every authority for this execution.
    machine = live_machine(name)
    spec_row = managed_spec(name)
    action_id = diagnostics_action(name, machine, spec_row)
    argv = resolve(action_id, name, spec_row)
    scope = "host-only" if action_id == "machine.diagnostics-host" else "host-and-guest"
    previous = diagnostics_directory()
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    completed = False

    def interrupted(signum: int, frame: Any) -> None:
        raise Refused("diagnostics collection was interrupted")

    handlers = {sig: signal.signal(sig, interrupted)
                for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        raw, _ = process.communicate(timeout=DIAGNOSTICS_TIMEOUT)
        completed = True
        if process.returncode != 0:
            raise Refused("diagnostics collection failed; no saved result was confirmed")
        try:
            payload = json.loads(raw, object_pairs_hook=unique_json)
        except (ValueError, TypeError):
            raise Refused("invalid diagnostics JSON") from None
        return diagnostics_result(payload, name, request_id, scope, previous)
    except subprocess.TimeoutExpired:
        raise Refused("diagnostics collection timed out") from None
    finally:
        try:
            if not completed:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
                except ProcessLookupError:
                    pass
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def detached(action_id: str) -> bool:
    return action_id in DETACHED_ACTIONS or action_id.startswith(
        DETACHED_PREFIXES
    )


def capabilities(name: str) -> dict[str, Any]:
    """Answer what this machine can actually do, and why it cannot."""
    machine = live_machine(name)
    spec_row = managed_spec(name)

    verbs: dict[str, Any] = {}
    for verb in VERBS:
        try:
            action_id = choose_action(verb, name, machine, spec_row)
        except Refused as exc:
            verbs[verb] = {
                "available": False,
                "reason": str(exc),
                "action_id": None,
                "destructive": verb in DESTRUCTIVE_VERBS,
            }
            continue

        try:
            # A resolvable action is the only kind this bridge will run, so a
            # registry that cannot resolve it is a real unavailability.
            resolve(action_id, name, spec_row)
        except Refused as exc:
            verbs[verb] = {
                "available": False,
                "reason": str(exc),
                "action_id": action_id,
                "destructive": verb in DESTRUCTIVE_VERBS,
            }
            continue

        verbs[verb] = {
            "available": True,
            "reason": "",
            "action_id": action_id,
            "destructive": verb in DESTRUCTIVE_VERBS,
        }

    # What the libvirt console actually shows. A VFIO guest's desktop is on
    # its passed-through GPU (Looking Glass or the physical output); the
    # console is its emulated display, useful for boot and login recovery.
    # Unknown VFIO state claims neither.
    vfio = machine.get("vfio")
    verbs["console"]["display"] = (
        "emulated-recovery" if vfio is True
        else "primary" if vfio is False
        else "unknown"
    )

    live_managed = machine.get("managed")
    return {
        "phase": "capabilities",
        "machine": {
            "name": name,
            "state": str(machine.get("state") or "unknown"),
            # Tri-state: None when the domain's own metadata could not be
            # read, never a guessed False.
            "managed": live_managed if isinstance(live_managed, bool) else None,
            "spec": spec_row is not None,
            "vfio": machine.get("vfio") if isinstance(machine.get("vfio"), bool) else None,
        },
        "verbs": verbs,
    }


MACHINE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
NUMBER = re.compile(r"^[1-9][0-9]{0,6}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def create_plan() -> dict[str, Any]:
    plan = cli_json("machine", "create-plan")
    if (
        not isinstance(plan, dict)
        or plan.get("schema") != 1
        or not isinstance(plan.get("templates"), list)
    ):
        raise Refused("invalid creation plan")
    return plan


def create(args: list[str]) -> None:
    """Record, project and provision one Machine; every value re-checked here
    against the plan, then again by the factory."""
    if len(args) not in (5, 8):
        raise Refused("usage: create TEMPLATE NAME LIFECYCLE NETWORK PROFILE [MEMORY VCPUS DISK]")
    template_id, name, lifecycle, network, profile = args[:5]
    for value in (template_id, lifecycle, network, profile):
        if not TOKEN.fullmatch(value):
            raise Refused("invalid creation request")
    if not MACHINE_ID.fullmatch(name):
        raise Refused("the name must be 2-31 lowercase letters, digits or dashes")
    if not all(NUMBER.fullmatch(value) for value in args[5:]):
        raise Refused("custom resources need memory, vCPUs and disk")

    plan = create_plan()
    matches = [entry for entry in plan["templates"]
               if isinstance(entry, dict) and entry.get("id") == template_id]
    if len(matches) != 1:
        raise Refused("unknown or unready Template")
    template = matches[0]
    if template.get("creatable") is not True:
        raise Refused(str(template.get("blocked_reason") or "the Template cannot be created"))
    if lifecycle not in template.get("lifecycles", []):
        raise Refused("the Template does not allow that lifecycle")
    if network not in template.get("network_profiles", []):
        raise Refused("the Template does not allow that network")
    if profile not in template.get("resource_profiles", []):
        raise Refused("the Template does not allow that resource profile")

    command = ["machine", "create", template_id, name, "--lifecycle", lifecycle,
               "--network-profile", network, "--resource-profile", profile]
    if profile == "custom":
        if len(args) != 8:
            raise Refused("custom resources need memory, vCPUs and disk")
        memory, vcpus, disk = (int(value) for value in args[5:])
        limits = template.get("custom")
        keys = ("memory_mb_min", "vcpus_min", "vcpus_max", "disk_gib_min")
        if not isinstance(limits, dict) or not all(
                type(limits.get(key)) is int for key in keys):
            raise Refused("the Template has no custom limits")
        if memory < limits["memory_mb_min"]:
            raise Refused(f"memory must be at least {limits['memory_mb_min']} MB")
        if not limits["vcpus_min"] <= vcpus <= limits["vcpus_max"]:
            raise Refused(f"vCPUs must be between {limits['vcpus_min']} and {limits['vcpus_max']}")
        if disk < limits["disk_gib_min"]:
            raise Refused(f"the disk must be at least {limits['disk_gib_min']} GiB")
        command += ["--memory-mb", str(memory), "--vcpus", str(vcpus), "--disk-gib", str(disk)]
    elif len(args) != 5:
        raise Refused("only custom resources take values")
    mode = template.get("looking_glass_mode")
    if mode not in (None, "disabled"):
        command += ["--looking-glass-mode", str(mode)]

    # One staged call records and projects the Machine: the factory publishes
    # the record only after its spec is written, so a refusal leaves neither.
    command.append("--project")
    try:
        created = cli_json(*command)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"the factory did not answer: {exc}") from None
    machine = created.get("machine") if isinstance(created, dict) else None
    if (
        not isinstance(machine, dict)
        or machine.get("id") != name
        or created.get("spec") != f"vm-specs/.generated/{name}.yml"
        or type(created.get("record_sha256")) is not str
        or not SHA256.fullmatch(created["record_sha256"])
    ):
        raise Refused("the factory did not confirm the Machine and its spec")
    # The runner resolves the provisioning command itself; nothing else crosses.
    privileged("machine.provision", name)


def workbench() -> dict[str, Any]:
    """The Workbench registry joined with live state, for presentation only."""
    payload = cli_json("workbench", "list")
    rows = cli_json("vm", "list")
    if not isinstance(payload, dict) or not isinstance(rows, list):
        raise Refused("invalid Workbench or live inventory")
    live = {row.get("name"): row for row in rows if isinstance(row, dict)}
    candidates = []
    for row in payload.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        machine = live.get(row.get("domain"))
        runtime = str(machine.get("state") or "unknown").lower() if machine else "missing"
        candidates.append({**row, "runtime": runtime})
    return {
        "phase": "workbench",
        "available": payload.get("available") is True,
        "candidates": candidates,
        "errors": [str(error) for error in payload.get("errors") or []],
    }


def seal(name: str) -> None:
    """Hand one shut-off candidate to the reviewed seal playbook."""
    payload = cli_json("workbench", "list")
    if not isinstance(payload, dict):
        raise Refused("invalid Workbench registry")
    matches = [row for row in payload.get("candidates") or []
               if isinstance(row, dict) and row.get("domain") == name]
    if len(matches) != 1:
        raise Refused("not a Workbench candidate")
    if matches[0].get("state") != "candidate":
        raise Refused("already captured; release it before sealing again")
    state = str(live_machine(name).get("state") or "unknown").lower()
    if state != "shut off":
        raise Refused("shut the candidate down before sealing it")
    privileged("workbench.seal", name)


USB_PORT = re.compile(r"^[0-9]+-[0-9]+(\.[0-9]+)*$")
USB_SCOPES = ("once", "permanent")
USB_DEVICE = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{4}$")


def usb_devices() -> list[dict[str, Any]]:
    payload = cli_json("usb", "list")
    if not isinstance(payload, dict) or not isinstance(payload.get("devices"), list):
        raise Refused("invalid USB device list")
    devices = [row for row in payload["devices"]
               if isinstance(row, dict) and isinstance(row.get("port"), str)
               and USB_PORT.fullmatch(row["port"])]
    # Blocked first: those are the ones an operator comes here to allow.
    return sorted(devices, key=lambda row: row.get("authorized") != 0)


def usb() -> dict[str, Any]:
    """The host's USB devices as the kernel reports them, for presentation."""
    return {"phase": "usb", "devices": usb_devices()}


def usb_allow(port: str, scope: str, identity: str) -> None:
    """Hand one blocked device that is not a keyboard or mouse to the runner.

    The allow is bound to the device the operator saw (vendor:product), not
    to the port alone: another device plugged into that port meanwhile is
    refused here, and again by the playbook.
    """
    if len(port) > 32 or not USB_PORT.fullmatch(port):
        raise Refused("invalid USB port")
    if scope not in USB_SCOPES:
        raise Refused("the scope must be once or permanent")
    if not USB_DEVICE.fullmatch(identity):
        raise Refused("invalid USB device id")
    matches = [row for row in usb_devices() if row["port"] == port]
    if len(matches) != 1:
        raise Refused("no USB device is attached at that port")
    device = matches[0]
    if f"{device.get('vendor_id')}:{device.get('product_id')}" != identity:
        raise Refused("the device at that port is no longer the one shown")
    if device.get("authorized") != 0:
        raise Refused("the device is not blocked")
    if device.get("hid") is not False:
        raise Refused("a device that presents a keyboard or mouse is allowed only from a terminal")
    if not device.get("interfaces"):
        # A blocked device reports its interfaces from its descriptors; none
        # means they could not be read, which is never taken as harmless.
        raise Refused("what the device presents could not be read; allow it from a terminal")
    # The runner resolves the playbook itself; the playbook checks it again as root.
    privileged("usb.allow", f"usb:{port}:{scope}:{identity}")


PANIC_RESTORE_TIMEOUT = 180


def panic_summary(payload: Any) -> dict[str, Any]:
    """The emergency stop record, reduced to what the shell shows."""
    if not isinstance(payload, dict) or not isinstance(payload.get("engaged"), bool):
        raise Refused("invalid emergency stop answer")
    record = payload.get("record")
    domains = []
    engaged_at = None
    if payload["engaged"]:
        if not isinstance(record, dict) or not isinstance(record.get("domains"), dict):
            raise Refused("invalid emergency stop record")
        engaged_at = record.get("engaged_at")
        for name, entry in sorted(record["domains"].items()):
            if not isinstance(entry, dict):
                raise Refused("invalid emergency stop record")
            domains.append({
                "name": str(name),
                "paused": entry.get("paused") is True,
                "links_down": len(entry.get("links_down") or []),
            })
    return {
        "engaged": payload["engaged"],
        "engaged_at": engaged_at if isinstance(engaged_at, (int, float)) else None,
        "domains": domains,
        "failures": [str(item) for item in payload.get("failures") or []],
        "notes": [str(item) for item in payload.get("notes") or []],
    }


def panic_status() -> dict[str, Any]:
    return {"phase": "panic", **panic_summary(cli_json("panic", "status"))}


def panic_restore() -> int:
    """Run the confirmed restore and report what is left, if anything.

    A partial restore exits non-zero with its JSON still on stdout, so it is
    read either way; anything else that fails is a refusal.
    """
    result = subprocess.run(
        [HYPERLABCTL, "--json", "panic", "restore", "--confirm"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=PANIC_RESTORE_TIMEOUT,
    )
    if result.returncode not in (0, 1):
        raise Refused(result.stderr.strip() or "the emergency stop could not be restored")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Refused("invalid hyperlabctl JSON") from exc
    emit({"phase": "panic-restore", "ok": result.returncode == 0, **panic_summary(payload)})
    return 0 if result.returncode == 0 else 1


def checkout() -> str:
    value = CHECKOUT_POINTER.read_text(encoding="utf-8").strip()
    candidate = Path(value)
    if not candidate.is_absolute() or not candidate.is_dir():
        raise Refused("invalid HyperLab checkout")
    return str(candidate)


def privileged(action_id: str, name: str) -> None:
    # The runner re-resolves the action; argv never crosses this boundary.
    os.execv(OPERATION, [OPERATION, "launch", action_id, name])


def valid_name(name: str) -> None:
    if not name or len(name) > 255:
        raise Refused("invalid machine name")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise Refused("invalid machine name")


def main() -> int:
    if sys.argv[1:] == ["operations"]:
        os.execv(OPERATION, [OPERATION, "operations"])
    if len(sys.argv) == 3 and sys.argv[1] == "operation":
        os.execv(OPERATION, [OPERATION, "operation", sys.argv[2]])
    if len(sys.argv) == 3 and sys.argv[1] == "operation-view":
        # Reattach an observer; the runner validates the id and owns nothing new.
        os.execv(OPERATION, [OPERATION, "view", sys.argv[2]])
    if sys.argv[1:] == ["workbench"]:
        emit(workbench())
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "seal":
        valid_name(sys.argv[2])
        seal(sys.argv[2])
        return 127
    if sys.argv[1:] == ["panic-status"]:
        emit(panic_status())
        return 0
    if sys.argv[1:] == ["panic-restore"]:
        return panic_restore()
    if sys.argv[1:] == ["usb"]:
        emit(usb())
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "usb-allow":
        usb_allow(sys.argv[2], sys.argv[3], sys.argv[4])
        return 127
    if sys.argv[1:] == ["create-plan"]:
        emit({"phase": "create-plan", "plan": create_plan()})
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "create":
        create(sys.argv[2:])
        return 127
    if len(sys.argv) == 4 and sys.argv[1] == "diagnostics":
        try:
            emit(collect_diagnostics(sys.argv[2], sys.argv[3]))
        except (Refused, OSError, subprocess.TimeoutExpired):
            # Neither collector stderr nor inventory errors enter presentation.
            emit({"phase": "refused", "reason": "Diagnostics could not be collected"})
            return 2
        return 0
    if len(sys.argv) != 3:
        raise Refused("usage: machine-action {capabilities|VERB} MACHINE")

    verb = sys.argv[1]
    name = sys.argv[2]

    valid_name(name)

    if verb == "capabilities":
        emit(capabilities(name))
        return 0

    if verb == "diagnostics":
        raise Refused("diagnostics require a request id")

    if verb == "stream-health":
        # Read only: the same checks as restarting the capture, then the
        # reviewed health command. The shell shows the answer as it came.
        machine = live_machine(name)
        choose_action("restart-capture", name, machine, managed_spec(name))
        report = cli_json("looking-glass", "health", name, timeout=45)
        if not isinstance(report, dict):
            raise Refused("invalid stream health report")
        emit({"phase": "stream-health", "machine": name, "health": report})
        return 0

    if verb == "clipboard":
        # The same checks as SSH: the text travels over that channel.
        machine = live_machine(name)
        choose_action("ssh", name, machine, managed_spec(name))
        argv = resolve("vm.clipboard-send", name, None)
        emit({"phase": "accepted", "mode": "foreground", "verb": "clipboard",
              "machine": name, "action_id": "vm.clipboard-send"})
        os.execvp(argv[0], argv)
        return 127

    if verb not in VERBS:
        raise Refused("unsupported machine operation")

    machine = live_machine(name)
    spec_row = managed_spec(name)
    action_id = choose_action(verb, name, machine, spec_row)
    argv = resolve(action_id, name, spec_row)

    if detached(action_id):
        privileged(action_id, name)
        return 127

    emit({
        "phase": "accepted",
        "mode": "connection" if verb in CONNECTION_VERBS else "foreground",
        "verb": verb,
        "machine": name,
        "action_id": action_id,
    })

    os.execvp(argv[0], argv)
    return 127


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Refused, OSError, subprocess.TimeoutExpired) as exc:
        emit({"phase": "refused", "reason": str(exc)})
        print(f"HyperLab: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
