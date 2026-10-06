"""Emergency stop: pause every running Machine and cut its network (ADR 0047).

engage    for each running domain, set every interface link down, then pause
          the domain; record exactly what was changed
status    the record, if an emergency stop is engaged
restore   with --confirm only: set up the links the record set down, resume
          the domains the record paused, then remove the record

Everything is reversible and runs as the operator against qemu:///system.
Nothing here destroys or shuts down a domain, touches a domain that was not
running at engage time, or changes a libvirt network. Link changes are live
only (no --config), so a domain that is restarted comes back with the links
its definition has.

The order is fail-safe: a link goes down before the domain is paused, a
failure on one domain never stops the others, and every failure is reported
and makes the command exit non-zero. The record is written after every
change, so a crash in the middle never loses what there is to restore, and
engaging again keeps it and adds to it.
"""

import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path

from ..errors import ContractError, Unavailable
from .base import Command

SCHEMA = 1
RECORD_NAME = "panic.json"
MAX_RECORD_BYTES = 256 * 1024
VIRSH_TIMEOUT = 15
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def _runtime_dir(environ):
    runtime = Path(environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
    if not runtime.is_absolute():
        raise Unavailable("XDG_RUNTIME_DIR is not an absolute path")
    return runtime


def _private_dir(environ, create):
    """The operator's private HyperLab runtime directory, 0700 and owned."""
    runtime = _runtime_dir(environ)
    try:
        info = runtime.lstat()
    except OSError as exc:
        raise Unavailable("the runtime directory is unavailable: %s" % exc) from exc
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise Unavailable("the runtime directory is not a directory of this user")
    directory = runtime / "hyperlab"
    if create:
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise Unavailable("cannot create %s: %s" % (directory, exc)) from exc
    try:
        info = directory.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise Unavailable("cannot inspect %s: %s" % (directory, exc)) from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise Unavailable("%s is not a private directory of this user" % directory)
    return directory


def record_path(environ):
    return _runtime_dir(environ) / "hyperlab" / RECORD_NAME


def _valid_record(data):
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return False
    if set(data) != {"schema", "engaged_at", "updated_at", "domains"}:
        return False
    for key in ("engaged_at", "updated_at"):
        if type(data[key]) not in (int, float) or data[key] <= 0:
            return False
    if not isinstance(data["domains"], dict):
        return False
    for name, entry in data["domains"].items():
        if not isinstance(name, str) or not name or len(name) > 255:
            return False
        if not isinstance(entry, dict) or set(entry) != {"links_down", "paused"}:
            return False
        if entry["paused"] is not True and entry["paused"] is not False:
            return False
        if not isinstance(entry["links_down"], list):
            return False
        for link in entry["links_down"]:
            if (not isinstance(link, dict) or set(link) != {"mac", "interface"}
                    or not isinstance(link["mac"], str) or not MAC_RE.fullmatch(link["mac"])
                    or not isinstance(link["interface"], str)):
                return False
    return True


def read_record(environ):
    """The engaged record, or None when no emergency stop is engaged."""
    directory = _private_dir(environ, create=False)
    if directory is None:
        return None
    path = directory / RECORD_NAME
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise Unavailable("cannot open %s: %s" % (path, exc)) from exc
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_RECORD_BYTES):
            raise Unavailable("%s is not a private record of this user" % path)
        try:
            data = json.loads(stream.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Unavailable("%s is not valid JSON" % path) from exc
    if not _valid_record(data):
        raise Unavailable("%s is not a valid emergency stop record" % path)
    return data


def write_record(environ, record):
    directory = _private_dir(environ, create=True)
    fd, name = tempfile.mkstemp(prefix=".panic-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / RECORD_NAME)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def remove_record(environ):
    directory = _private_dir(environ, create=False)
    if directory is not None:
        try:
            (directory / RECORD_NAME).unlink()
        except FileNotFoundError:
            pass


def _virsh(ctx, *args):
    return ctx.virsh_uncached(*args, timeout=VIRSH_TIMEOUT)


def _why(result):
    lines = (result.stderr or result.stdout or "").strip().splitlines()
    return lines[-1] if lines else "exit %d" % result.rc


def running_domains(ctx):
    result = _virsh(ctx, "list", "--state-running", "--name")
    if not result.ok:
        raise Unavailable("the running domains could not be listed: %s" % _why(result))
    return result.lines()


def interfaces(ctx, domain):
    """(interface, mac) for every interface of a running domain."""
    result = _virsh(ctx, "domiflist", domain)
    if not result.ok:
        raise Unavailable("%s: its interfaces could not be listed: %s" % (domain, _why(result)))
    found = []
    for line in result.lines():
        fields = line.split()
        if len(fields) >= 2 and MAC_RE.fullmatch(fields[-1].lower()):
            found.append((fields[0], fields[-1].lower()))
    return found


def link_state(ctx, domain, mac):
    """"up", "down", or None when the state could not be read."""
    result = _virsh(ctx, "domif-getlink", domain, mac)
    if not result.ok or not result.lines():
        return None
    word = result.lines()[-1].split()[-1].lower()
    return word if word in ("up", "down") else None


def domain_state(ctx, domain):
    result = _virsh(ctx, "domstate", domain)
    if not result.ok:
        return None
    return (result.stdout.strip() or "unknown").lower()


def engage(ctx, environ, now=time.time):
    """Cut and pause every running domain. Returns (record, failures).

    The stop never waits on its record: a record that cannot be read or
    written is a reported failure, and every running domain is still cut and
    paused. An unreadable record is left as it is, never overwritten, and
    what this press changed is then only in the output.
    """
    failures = []
    recording = True
    try:
        record = read_record(environ)
    except Unavailable as exc:
        failures.append("the emergency stop record is unreadable (%s); stopping without "
                        "recording, so Restore cannot undo this press: resume by hand" % exc)
        record, recording = None, False
    if record is None:
        record = {"schema": SCHEMA, "engaged_at": now(), "updated_at": now(), "domains": {}}
    record["updated_at"] = now()

    def save():
        nonlocal recording
        if not recording:
            return
        try:
            write_record(environ, record)
        except (Unavailable, OSError) as exc:
            failures.append("the emergency stop record could not be written (%s); stopping "
                            "without recording, so Restore cannot undo this press: resume by hand"
                            % exc)
            recording = False

    # Recorded before anything changes: the shell shows the stop at once,
    # and a crash below still leaves something to restore from.
    save()
    try:
        domains = running_domains(ctx)
    except Unavailable as exc:
        return record, [str(exc)]

    for domain in domains:
        entry = record["domains"].get(domain) or {"links_down": [], "paused": False}
        recorded = {link["mac"] for link in entry["links_down"]}
        try:
            links = interfaces(ctx, domain)
        except Unavailable as exc:
            failures.append(str(exc))
            links = []
        for interface, mac in links:
            # A link the operator had already set down stays theirs: it is
            # not recorded, so restore does not bring it up.
            if link_state(ctx, domain, mac) == "down":
                continue
            result = _virsh(ctx, "domif-setlink", domain, mac, "down")
            if not result.ok:
                failures.append("%s: link %s (%s) could not be set down: %s"
                                % (domain, interface, mac, _why(result)))
                continue
            if mac not in recorded:
                entry["links_down"].append({"mac": mac, "interface": interface})
                recorded.add(mac)
            record["domains"][domain] = entry
            save()
        # Paused after its links are down, never before.
        result = _virsh(ctx, "suspend", domain)
        if result.ok:
            entry["paused"] = True
            record["domains"][domain] = entry
            save()
        else:
            failures.append("%s: could not be paused: %s" % (domain, _why(result)))
    return record, failures


def restore(ctx, environ, confirm):
    """Undo exactly what the record says. Returns (record or None, failures, notes)."""
    if not confirm:
        raise ContractError("restoring needs --confirm: it resumes every Machine the "
                            "emergency stop paused and reconnects its network")
    record = read_record(environ)
    if record is None:
        return None, [], ["no emergency stop is engaged; nothing to restore"]
    failures = []
    notes = []
    for domain in sorted(record["domains"]):
        entry = record["domains"][domain]
        state = domain_state(ctx, domain)
        if state not in ("running", "paused"):
            # Gone, shut off or crashed: its live link state went with it and
            # there is nothing to resume.
            notes.append("%s is %s now; nothing restored for it"
                         % (domain, state or "no longer defined"))
            del record["domains"][domain]
            continue
        for link in list(entry["links_down"]):
            result = _virsh(ctx, "domif-setlink", domain, link["mac"], "up")
            if result.ok:
                entry["links_down"].remove(link)
            else:
                failures.append("%s: link %s (%s) could not be set up: %s"
                                % (domain, link["interface"], link["mac"], _why(result)))
        if entry["paused"]:
            if state == "paused":
                result = _virsh(ctx, "resume", domain)
                if result.ok:
                    entry["paused"] = False
                else:
                    failures.append("%s: could not be resumed: %s" % (domain, _why(result)))
            else:
                notes.append("%s was already running again" % domain)
                entry["paused"] = False
        if not entry["links_down"] and not entry["paused"]:
            del record["domains"][domain]
    if record["domains"]:
        # What could not be restored stays recorded, so restore can be run again.
        write_record(environ, record)
        return record, failures, notes
    remove_record(environ)
    return None, failures, notes


def _summary(record):
    if record is None:
        return "No emergency stop is engaged."
    lines = ["Emergency stop engaged at %s." % time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(record["engaged_at"]))]
    for domain in sorted(record["domains"]):
        entry = record["domains"][domain]
        links = ", ".join(link["interface"] for link in entry["links_down"]) or "none"
        lines.append("  %-28s %-8s links down: %s"
                     % (domain, "paused" if entry["paused"] else "running", links))
    return "\n".join(lines)


class PanicCommand(Command):
    name = "panic"
    help = "emergency stop: pause every running Machine and cut its network"
    order = 13

    def configure(self, parser):
        sub = parser.add_subparsers(dest="panic_action", required=True)
        sub.add_parser("engage", help="pause every running domain after cutting its links")
        sub.add_parser("status", help="what the emergency stop changed, if engaged")
        restore_parser = sub.add_parser("restore", help="undo exactly what engage changed")
        restore_parser.add_argument("--confirm", action="store_true",
                                    help="required: resume and reconnect")

    def run(self, args, ctx):
        environ = ctx.environ
        failures, notes = [], []
        if args.panic_action == "engage":
            record, failures = engage(ctx, environ)
        elif args.panic_action == "restore":
            record, failures, notes = restore(ctx, environ, args.confirm)
        else:
            record = read_record(environ)
        if args.json:
            print(json.dumps({"engaged": record is not None, "record": record,
                              "failures": failures, "notes": notes}, indent=2))
        else:
            print(_summary(record))
            for note in notes:
                print("note: %s" % note)
            for failure in failures:
                print("FAILED: %s" % failure)
        return 1 if failures else 0
