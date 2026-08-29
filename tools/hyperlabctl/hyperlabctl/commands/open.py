"""Open fixed graphical HyperLab shell surfaces through the authoritative CLI.

The launcher drawer and full Control Center are one single-instance GTK4 Layer
Shell application. Every target remains a fixed argv element; user-controlled
domain names never enter a shell program.
"""

import json
import os
import shlex
import shutil
import stat
import subprocess
import time
from pathlib import Path

from ..composer import find_spec, image_entry
from ..config import load_yaml
from ..errors import Unavailable
from ..inventory import domain_detail
from .base import Command


_MANAGER = "/usr/local/bin/privatestack-hyperlab-domains"
_LOOKING_GLASS_CLIENT = "/usr/local/bin/looking-glass-client"
_SECTIONS = (
    "overview",
    "domains",
    "vms",
    "create",
    "images",
    "policies",
    "gpu",
    "activity",
    "diagnostics",
)
_SURFACES = ("drawer", "overlay")


_SSH_READY_TIMEOUT_SECONDS = 30.0
_SSH_READY_PROBE_TIMEOUT_SECONDS = 2.0
_SSH_READY_RETRY_SECONDS = 0.5
_SSH_TRANSIENT_ERRORS = (
    "connection refused",
    "connection timed out",
    "operation timed out",
    "no route to host",
    "network is unreachable",
    "connection reset by peer",
    "connection closed by",
)


def _executable(command):
    if "/" in command:
        path = Path(command)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise Unavailable("graphical helper is unavailable: %s" % command)
        return str(path)
    resolved = shutil.which(command)
    if resolved is None:
        raise Unavailable("graphical helper is unavailable: %s" % command)
    return resolved


def _runtime_inventory_path(domain):
    runtime = Path(
        os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
    )

    try:
        info = runtime.lstat()
    except OSError as exc:
        raise Unavailable(
            "runtime directory is unavailable: %s" % runtime
        ) from exc

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise Unavailable(
            "runtime directory is not a real directory: %s" % runtime
        )
    if info.st_uid != os.getuid():
        raise Unavailable(
            "runtime directory is not owned by the current user: %s" % runtime
        )

    return runtime / (domain + ".ini")


def _validate_runtime_inventory(inventory, domain):
    try:
        info = inventory.lstat()
    except OSError as exc:
        raise Unavailable(
            "runtime SSH inventory is unavailable for %s: %s"
            % (domain, inventory)
        ) from exc

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise Unavailable(
            "runtime SSH inventory is not a regular file for %s: %s"
            % (domain, inventory)
        )
    if info.st_uid != os.getuid():
        raise Unavailable(
            "runtime SSH inventory has the wrong owner for %s: %s"
            % (domain, inventory)
        )
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise Unavailable(
            "runtime SSH inventory has the wrong mode for %s: %s"
            % (domain, inventory)
        )

    return inventory


def _publish_runtime_inventory(ctx, domain, inventory):
    repo_value = ctx.config.repo_root
    if repo_value is None:
        raise Unavailable(
            "no HyperLab checkout is available for inventory recovery"
        )

    repo_root = Path(repo_value).resolve()
    spec_path = find_spec(repo_root, domain)
    hyperlabctl = _executable("hyperlabctl")

    try:
        result = subprocess.run(
            [
                hyperlabctl,
                "--repo",
                str(repo_root),
                "vm",
                "inventory",
                spec_path,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=35.0,
        )
    except subprocess.TimeoutExpired as exc:
        raise Unavailable(
            "runtime inventory recovery timed out for %s" % domain
        ) from exc

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "hyperlabctl vm inventory failed"
        )
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise Unavailable(
            "runtime inventory recovery failed for %s: %s"
            % (domain, detail)
        )

    return _validate_runtime_inventory(inventory, domain)


def _runtime_inventory(ctx, domain):
    inventory = _runtime_inventory_path(domain)

    try:
        inventory.lstat()
    except FileNotFoundError:
        return _publish_runtime_inventory(ctx, domain, inventory)
    except OSError as exc:
        raise Unavailable(
            "cannot inspect runtime SSH inventory for %s: %s"
            % (domain, inventory)
        ) from exc

    return _validate_runtime_inventory(inventory, domain)

def _ssh_argv(ctx, domain):
    repo_root = ctx.config.repo_root
    if repo_root is None:
        raise Unavailable("no HyperLab checkout is available for SSH resolution")
    base_inventory = Path(repo_root) / "inventory.ini"
    if base_inventory.is_symlink() or not base_inventory.is_file():
        raise Unavailable("base inventory is unavailable: %s" % base_inventory)
    runtime_inventory = _runtime_inventory(ctx, domain)
    ansible_inventory = _executable("ansible-inventory")
    result = subprocess.run(
        [
            ansible_inventory,
            "-i",
            str(base_inventory),
            "-i",
            str(runtime_inventory),
            "--host",
            domain,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5.0,
    )
    if result.returncode != 0:
        raise Unavailable(
            "cannot resolve SSH inventory for %s: %s"
            % (domain, result.stderr.strip() or "ansible-inventory failed")
        )
    try:
        hostvars = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Unavailable("SSH inventory returned invalid JSON") from exc

    host = str(hostvars.get("ansible_host") or domain)
    user = str(hostvars.get("ansible_user") or os.environ.get("USER") or "")
    if not user:
        raise Unavailable("SSH inventory does not declare ansible_user")

    argv = ["ssh"]
    for key in ("ansible_ssh_common_args", "ansible_ssh_extra_args"):
        raw = hostvars.get(key)
        if raw:
            argv.extend(shlex.split(str(raw)))

    private_key = hostvars.get("ansible_ssh_private_key_file")
    if private_key:
        argv.extend(["-i", str(private_key)])
    port = hostvars.get("ansible_port")
    if port:
        argv.extend(["-p", str(port)])
    argv.append("%s@%s" % (user, host))
    return argv


def _wait_for_ssh_ready(ssh_argv, domain):
    # Retry only transient post-boot transport failures. Inventory resolution
    # already proved the managed identity and address; authentication and host
    # key failures remain immediate refusals.
    deadline = time.monotonic() + _SSH_READY_TIMEOUT_SECONDS
    last_detail = "SSH service did not answer"

    while True:
        probe = [
            *ssh_argv[:-1],
            "-T",
            "-o",
            "ConnectTimeout=1",
            "-o",
            "ConnectionAttempts=1",
            ssh_argv[-1],
            "true",
        ]

        try:
            result = subprocess.run(
                probe,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=_SSH_READY_PROBE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            detail = "SSH readiness probe timed out"
        else:
            if result.returncode == 0:
                return

            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or "SSH readiness probe failed"
            )
            lowered = detail.lower()
            if not any(token in lowered for token in _SSH_TRANSIENT_ERRORS):
                raise Unavailable(
                    "SSH readiness probe failed for %s: %s"
                    % (domain, detail[-1200:])
                )

        last_detail = detail[-1200:]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Unavailable(
                "SSH did not become ready for %s within %.0f seconds: %s"
                % (domain, _SSH_READY_TIMEOUT_SECONDS, last_detail)
            )

        time.sleep(min(_SSH_READY_RETRY_SECONDS, remaining))


def _require_running_vfio(ctx, domain):
    detail = domain_detail(ctx, domain)
    if str(detail.get("state") or "").lower() != "running":
        raise Unavailable("%s is not running" % domain)
    if not detail.get("vfio"):
        raise Unavailable("%s is not a VFIO guest" % domain)


_LINUX_LOOKING_GLASS_PRELOGIN_EXIT = 20

_LINUX_LOOKING_GLASS_PREPARE = r"""set -euo pipefail

refuse() {
    printf 'REFUSAL: %s\n' "$1" >&2
    exit 1
}

prelogin_fallback() {
    printf 'FALLBACK: graphical user session is not ready; use SPICE display fallback\n' >&2
    exit 20
}

uid="$(id -u)"
export XDG_RUNTIME_DIR="/run/user/$uid"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

refresh_graphical_environment() {
    while IFS='=' read -r key value; do
        case "$key" in
            HYPRLAND_INSTANCE_SIGNATURE|WAYLAND_DISPLAY|XDG_CURRENT_DESKTOP|XDG_SESSION_TYPE)
                export "$key=$value"
                ;;
        esac
    done < <(systemctl --user show-environment)
}

graphical_session_ready() {
    pgrep -u "$uid" -x Hyprland >/dev/null 2>&1 &&
        [[ -n "${WAYLAND_DISPLAY:-}" ]] &&
        [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]
}

refresh_graphical_environment

if ! graphical_session_ready; then
    prelogin_fallback
fi

pgrep -u "$uid" -x Hyprland >/dev/null 2>&1 ||
    refuse "Hyprland did not become ready for Looking Glass"

[[ -n "${WAYLAND_DISPLAY:-}" ]] ||
    refuse "Wayland display is missing from the user session"

[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] ||
    refuse "Hyprland instance signature is missing from the user session"

[[ -x /usr/local/bin/looking-glass-host ]] ||
    refuse "Looking Glass Linux sender is not installed"

[[ -c /dev/kvmfr0 ]] ||
    refuse "guest KVMFR device is unavailable"

[[ -r /dev/kvmfr0 && -w /dev/kvmfr0 ]] ||
    refuse "guest KVMFR device is not accessible to the graphical user"

monitor_dump="$(hyprctl monitors 2>&1)" ||
    refuse "Hyprland monitor query failed"

grep -Fq "Monitor HEADLESS-0" <<<"$monitor_dump" ||
    refuse "reviewed HEADLESS-0 capture output is unavailable"

grep -Eq '1920x1080@144([.]0+)?' <<<"$monitor_dump" ||
    refuse "HEADLESS-0 is not using the reviewed 1920x1080@144 mode"

sender_running() {
    pgrep \
        -u "$uid" \
        -f '^/usr/local/bin/looking-glass-host([[:space:]]|$)' \
        >/dev/null
}

if sender_running; then
    exit 0
fi

mkdir -p "$HOME/.local/state/hyperlab"

# The detached wrapper is session-bound by behavior: it owns the sender PID
# and stops it as soon as the reviewed Hyprland compositor disappears. This
# prevents a stale KVMFR producer from surviving logout while avoiding a
# persistent user service or a broad process-kill policy.
nohup bash -s -- "$HOME/.local/state/hyperlab/looking-glass-host.log" \
    >/dev/null 2>&1 </dev/null <<'HYPERLAB_LG_SUPERVISOR' &
set -u

log_path=$1

/usr/local/bin/looking-glass-host \
    >"$log_path" 2>&1 </dev/null &
sender_pid=$!

cleanup() {
    if kill -0 "$sender_pid" >/dev/null 2>&1; then
        kill "$sender_pid" >/dev/null 2>&1 || true
    fi
    wait "$sender_pid" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM HUP

while kill -0 "$sender_pid" >/dev/null 2>&1; do
    if ! pgrep -u "$(id -u)" -x Hyprland >/dev/null 2>&1; then
        exit 0
    fi
    sleep 0.5
done

wait "$sender_pid" >/dev/null 2>&1 || true
HYPERLAB_LG_SUPERVISOR

for _ in 1 2 3 4 5; do
    sleep 1

    if sender_running; then
        sleep 1

        if sender_running; then
            exit 0
        fi
    fi
done

tail -n 40 \
    "$HOME/.local/state/hyperlab/looking-glass-host.log" \
    >&2 2>/dev/null || true

refuse "Looking Glass Linux sender did not remain running"
"""



def _spice_socket_for_domain(domain):
    virsh = _executable("virsh")
    result = subprocess.run(
        [
            virsh,
            "--connect",
            "qemu:///system",
            "domdisplay",
            "--type",
            "spice",
            domain,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise Unavailable(
            "cannot resolve the live SPICE endpoint for %s%s"
            % (domain, ": %s" % detail if detail else "")
        )

    uri = result.stdout.strip()
    prefix = "spice+unix://"
    if not uri.startswith(prefix):
        raise Unavailable(
            "refusing non-UNIX SPICE endpoint for %s: %s"
            % (domain, uri or "missing")
        )

    socket_path = uri[len(prefix):]
    if not socket_path.startswith("/"):
        raise Unavailable(
            "refusing non-absolute SPICE socket for %s: %s"
            % (domain, socket_path or "missing")
        )
    if not os.path.exists(socket_path):
        raise Unavailable(
            "SPICE socket for %s is not present: %s"
            % (domain, socket_path)
        )
    if not os.access(socket_path, os.R_OK | os.W_OK):
        raise Unavailable(
            "SPICE socket for %s is not accessible to the operator: %s"
            % (domain, socket_path)
        )
    return socket_path

def _looking_glass_transport(ctx, domain):
    repo_root = ctx.config.repo_root
    if repo_root is None:
        raise Unavailable(
            "no HyperLab checkout is available for Looking Glass resolution"
        )

    spec_path = find_spec(repo_root, domain)
    spec = load_yaml(repo_root / spec_path)

    if not isinstance(spec, dict):
        raise Unavailable(
            "Looking Glass VM specification is not a mapping"
        )

    image = image_entry(repo_root, spec.get("image"))

    if not isinstance(image, dict):
        raise Unavailable(
            "Looking Glass image manifest is not a mapping"
        )

    if str(spec.get("device_profile") or "") != "vfio":
        raise Unavailable(
            "Looking Glass requires a managed VFIO specification"
        )

    if not spec.get("looking_glass"):
        raise Unavailable(
            "Looking Glass is disabled by the VM specification"
        )

    os_family = str(image.get("os_family") or "")
    mode = str(spec.get("looking_glass_mode") or "")

    if os_family == "windows":
        return "windows"

    if os_family == "linux" and mode == "linux-experimental":
        return "linux-experimental"

    raise Unavailable(
        "the VM does not declare an approved Looking Glass transport"
    )



_LINUX_LOOKING_GLASS_SESSION_WAIT = r"""set -euo pipefail

uid="$(id -u)"
export XDG_RUNTIME_DIR="/run/user/$uid"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

refresh_graphical_environment() {
    while IFS='=' read -r key value; do
        case "$key" in
            HYPRLAND_INSTANCE_SIGNATURE|WAYLAND_DISPLAY|XDG_CURRENT_DESKTOP|XDG_SESSION_TYPE)
                export "$key=$value"
                ;;
        esac
    done < <(systemctl --user show-environment)
}

for _ in $(seq 1 240); do
    refresh_graphical_environment

    if pgrep -u "$uid" -x Hyprland >/dev/null 2>&1 &&
       [[ -n "${WAYLAND_DISPLAY:-}" ]] &&
       [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
        monitor_dump="$(hyprctl monitors 2>/dev/null || true)"

        if grep -Fq "Monitor HEADLESS-0" <<<"$monitor_dump" &&
           grep -Eq '1920x1080@144([.]0+)?' <<<"$monitor_dump"; then
            exit 0
        fi
    fi

    sleep 0.5
done

printf 'REFUSAL: reviewed Hyprland HEADLESS-0 did not become ready after SPICE login\n' >&2
exit 1
"""


def _stop_owned_process(process):
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _wait_for_linux_looking_glass_login(ctx, domain):
    ssh_argv = _ssh_argv(ctx, domain)
    _wait_for_ssh_ready(ssh_argv, domain)

    viewer_argv = [
        "virt-viewer",
        "--connect",
        "qemu:///system",
        "--wait",
        domain,
    ]
    viewer_executable = _executable(viewer_argv[0])
    viewer = subprocess.Popen(
        [viewer_executable, *viewer_argv[1:]],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    waiter = None
    try:
        waiter = subprocess.Popen(
            [*ssh_argv, "bash", "-s"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        if waiter.stdin is None:
            raise Unavailable(
                "Linux Looking Glass login waiter could not open its SSH input"
            )

        waiter.stdin.write(_LINUX_LOOKING_GLASS_SESSION_WAIT)
        waiter.stdin.close()

        deadline = time.monotonic() + 125
        while True:
            returncode = waiter.poll()
            if returncode is not None:
                break

            if viewer.poll() is not None:
                _stop_owned_process(waiter)
                raise Unavailable(
                    "temporary SPICE login console closed before "
                    "the guest graphical session became ready"
                )

            if time.monotonic() >= deadline:
                _stop_owned_process(waiter)
                raise Unavailable(
                    "guest graphical session did not become ready "
                    "within the SPICE login window"
                )

            time.sleep(0.25)

        stdout = waiter.stdout.read() if waiter.stdout is not None else ""
        stderr = waiter.stderr.read() if waiter.stderr is not None else ""

        if returncode != 0:
            detail = stderr.strip() or stdout.strip() or "remote login wait failed"
            if len(detail) > 1200:
                detail = detail[-1200:]
            raise Unavailable(
                "guest graphical session did not become ready for %s: %s"
                % (domain, detail)
            )
    finally:
        if waiter is not None and waiter.poll() is None:
            _stop_owned_process(waiter)
        _stop_owned_process(viewer)


def _prepare_linux_looking_glass(ctx, domain):
    ssh_argv = _ssh_argv(ctx, domain)
    _wait_for_ssh_ready(ssh_argv, domain)

    try:
        result = subprocess.run(
            [*ssh_argv, "bash", "-s"],
            input=_LINUX_LOOKING_GLASS_PREPARE,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        raise Unavailable(
            "Looking Glass sender preparation timed out for %s" % domain
        ) from exc

    if result.returncode == 0:
        return True

    if result.returncode == _LINUX_LOOKING_GLASS_PRELOGIN_EXIT:
        return False

    detail = (
        result.stderr.strip()
        or result.stdout.strip()
        or "remote sender preparation failed"
    )

    if len(detail) > 1200:
        detail = detail[-1200:]

    raise Unavailable(
        "Looking Glass sender preparation failed for %s: %s"
        % (domain, detail)
    )


class OpenCommand(Command):
    name = "open"
    help = "open fixed graphical HyperLab shell surfaces"
    order = 17

    def configure(self, parser):
        sub = parser.add_subparsers(dest="open_action", required=True)
        manager = sub.add_parser(
            "manager",
            help="toggle the Waybar drawer or full Layer Shell Control Center",
        )
        manager.add_argument("--surface", choices=_SURFACES, default="overlay")
        manager.add_argument("--section", choices=_SECTIONS, default="vms")
        console = sub.add_parser("console", help="open a libvirt graphical console")
        console.add_argument("domain")
        ssh = sub.add_parser("ssh", help="open an SSH terminal from runtime inventory")
        ssh.add_argument("domain")
        looking = sub.add_parser("looking-glass", help="open Looking Glass for one VFIO guest")
        looking.add_argument("domain")

    def run(self, args, ctx):
        if args.open_action == "manager":
            executable = _executable(_MANAGER)
            subprocess.Popen(
                [
                    executable,
                    "--surface",
                    args.surface,
                    "--section",
                    args.section,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return 0
        if args.open_action == "console":
            argv = [
                "virt-viewer",
                "--connect",
                "qemu:///system",
                "--wait",
                args.domain,
            ]
        elif args.open_action == "ssh":
            ssh_argv = _ssh_argv(ctx, args.domain)
            _wait_for_ssh_ready(ssh_argv, args.domain)
            argv = [
                "foot",
                "--app-id=hyperlab-operation",
                "--title=SSH · " + args.domain,
                *ssh_argv,
            ]
        else:
            _require_running_vfio(ctx, args.domain)
            transport = _looking_glass_transport(ctx, args.domain)
            if transport == "linux-experimental":
                sender_ready = _prepare_linux_looking_glass(
                    ctx,
                    args.domain,
                )
                if not sender_ready:
                    _wait_for_linux_looking_glass_login(
                        ctx,
                        args.domain,
                    )
                    sender_ready = _prepare_linux_looking_glass(
                        ctx,
                        args.domain,
                    )
                    if not sender_ready:
                        raise Unavailable(
                            "guest graphical session disappeared before "
                            "Looking Glass sender preparation"
                        )
            spice_socket = _spice_socket_for_domain(args.domain)
            argv = [
                _LOOKING_GLASS_CLIENT,
                "-F",
                "app:shmFile=/dev/kvmfr0",
                "spice:host=%s" % spice_socket,
                "spice:port=0",
                "spice:input=yes",
                "input:captureOnly=yes",
                "input:releaseKeysOnFocusLoss=yes",
            ]
            if transport == "linux-experimental":
                argv.append("egl:mapHDRtoSDR=no")

        executable = _executable(argv[0])
        os.execv(executable, [executable, *argv[1:]])
        raise AssertionError("os.execv unexpectedly returned")
