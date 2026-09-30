#!/usr/bin/env python3
"""Contract for the live focused-surface provenance binding.

The resolver, the launcher registration and the PID-bearing compositor
snapshot are pinned by their own contracts. This one pins the live chain that
joins them to the shell:

  compositor focus -> ShellState numbered request -> reviewed bridge
      -> resolver stream -> validated answer -> ProvenanceBadge / Diagnostics

It proves the stream answers one correlated line per request, re-reads the
registry for every request, never turns a failure into HOST and never exits
on hostile input; and it pins the bridge, its deployment and the QML wiring
that keeps compositor context and resolved provenance separate.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import select
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "tools/surface_provenance.py"
BRIDGE = ROOT / "roles/host_desktop_common/files/privatestack-surface-provenance.sh"
TASKS = ROOT / "roles/host_desktop_common/tasks/main.yml"
GROUP_VARS = ROOT / "group_vars/all/host-desktop.yml"
QML = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab"
OPEN = ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py"

BRIDGE_PATH = "/usr/local/bin/privatestack-surface-provenance"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab surface provenance live binding contract: {message}"
        )


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_resolver():
    spec = importlib.util.spec_from_file_location(
        "surface_provenance_live",
        RESOLVER,
    )

    require(
        spec is not None and spec.loader is not None,
        "cannot load resolver",
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def write_proc(proc: Path, pid: int, start: str, executable: Path) -> None:
    directory = proc / str(pid)
    directory.mkdir(parents=True)

    fields = ["S"] + ["0"] * 18 + [start, "0", "0"]

    (directory / "stat").write_text(
        f"{pid} (looking glass) " + " ".join(fields) + "\n",
        encoding="utf-8",
    )
    (directory / "exe").symlink_to(executable)


def write_registry(path: Path, entries: list[dict]) -> None:
    path.write_text(
        json.dumps({"version": 1, "entries": entries}),
        encoding="utf-8",
    )
    path.chmod(0o600)


def request(number, surface) -> str:
    return json.dumps({"request": number, "surface": surface}) + "\n"


class Stream:
    """The real resolver stream process, driven one line at a time."""

    def __init__(self, repo: Path, proc: Path, registry: Path) -> None:
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                str(RESOLVER),
                "--repo",
                str(repo),
                "--proc-root",
                str(proc),
                "stream",
                "--registry",
                str(registry),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def ask(self, line: str) -> dict:
        assert self.process.stdin is not None
        assert self.process.stdout is not None

        self.process.stdin.write(line)
        self.process.stdin.flush()

        ready, _, _ = select.select([self.process.stdout], [], [], 10)

        require(bool(ready), "stream did not answer a request interactively")

        answer = self.process.stdout.readline()

        require(answer.endswith("\n"), "stream answer is not one line")

        return json.loads(answer)

    def close(self) -> int:
        assert self.process.stdin is not None

        self.process.stdin.close()

        return self.process.wait(timeout=10)


def check_stream() -> None:
    resolver = load_resolver()

    with tempfile.TemporaryDirectory(prefix="hyperlab-live-") as name:
        temp = Path(name)
        repo = temp / "repo"
        proc = temp / "proc"
        runtime = temp / "runtime"
        (repo / "vm-specs").mkdir(parents=True)
        proc.mkdir()
        runtime.mkdir(mode=0o700)

        spec = repo / "vm-specs/arch-dev-vfio.yml"
        spec.write_text(
            yaml.safe_dump({
                "name": "arch-dev-vfio",
                "device_profile": "vfio",
                "network_profile": "dev",
                "looking_glass": True,
            }),
            encoding="utf-8",
        )
        digest = hashlib.sha256(spec.read_bytes()).hexdigest()

        # A process that is NOT the reviewed transport binary.
        impostor = temp / "impostor"
        impostor.write_text("#!/bin/sh\n", encoding="utf-8")
        write_proc(proc, 51001, "777", impostor)

        registry = runtime / "surface-provenance.json"
        stream = Stream(repo, proc, registry)

        host = {"pid": 51002, "app_id": "firefox", "window_id": "0x1"}
        managed = {
            "pid": 51001,
            "app_id": "looking-glass-client",
            "window_id": "0x2",
        }

        # No registry yet: host-native stays HOST, a managed-looking surface
        # fails closed.
        answer = stream.ask(request(1, host))
        require(
            answer["request"] == 1
            and answer["status"] == "ok"
            and answer["provenance"]["trust"] == "host"
            and answer["provenance"]["trust_source"] == "host-native",
            "host-native surface did not resolve to HOST",
        )

        answer = stream.ask(request(2, managed))
        require(
            answer["request"] == 2
            and answer["provenance"]["resolved"] is False
            and answer["provenance"]["trust"] is None
            and answer["provenance"]["reason"]
            == "managed-surface-not-registered",
            "unregistered managed surface did not fail closed",
        )

        # A registration published after the stream started is observed on
        # the very next request: the registry is never cached.
        write_registry(registry, [{
            "pid": 51001,
            "process_start_ticks": "777",
            "executable": "/usr/local/bin/looking-glass-client",
            "surface_kind": "looking-glass",
            "domain": "arch-dev-vfio",
            "spec_sha256": digest,
            "registered_by": "hyperlabctl",
        }])

        answer = stream.ask(request(3, managed))
        require(
            answer["provenance"]["resolved"] is False
            and answer["provenance"]["reason"]
            == "registered-executable-mismatch",
            "stream cached the registry or accepted an impostor executable",
        )

        # Window metadata never changes the answer.
        answer = stream.ask(request(4, {**managed, "app_id": "dev",
                                        "title": "DEV trusted"}))
        require(
            answer["provenance"]["trust"] is None,
            "window metadata influenced provenance",
        )

        # A tampered registry is unavailable for every surface; it never
        # degrades to HOST.
        registry.chmod(0o644)
        answer = stream.ask(request(5, host))
        require(
            answer["request"] == 5
            and answer["status"] == "unavailable"
            and "provenance" not in answer,
            "an untrusted registry did not make provenance unavailable",
        )
        registry.chmod(0o600)

        # Hostile lines are answered, attributed where possible, and never
        # end the stream.
        for line, number in (
            ("not json\n", None),
            ('{"request": 6}\n', None),
            ('{"request": true, "surface": {}}\n', None),
            ('{"request": 7, "surface": {"pid": "1"}}\n', 7),
            ('{"request": 8, "surface": {"pid": 1, "x": 1}}\n', 8),
            (request(9, {"pid": 1})[:-1] + " " * 17000 + "\n", None),
        ):
            answer = stream.ask(line)
            require(
                answer["status"] == "unavailable"
                and answer["request"] == number,
                f"hostile request was not refused in-band: {line[:40]!r}",
            )

        answer = stream.ask(request(10, {"pid": None,
                                         "app_id": "Looking-Glass-Client",
                                         "window_id": "0x3"}))
        require(
            answer["provenance"]["resolved"] is False
            and answer["provenance"]["reason"]
            == "managed-surface-without-pid",
            "a managed-looking surface without a PID resolved",
        )

        answer = stream.ask(request(11, {"pid": None, "app_id": "",
                                         "window_id": ""}))
        require(
            answer["provenance"]["trust"] == "host"
            and answer["provenance"]["reason"] == "no-focused-client",
            "an empty focus no longer resolves to host-native",
        )

        require(stream.close() == 0, "stream did not exit cleanly on EOF")

        # In-process, with the reviewed executable bound to a fixture binary:
        # a verified registration resolves DEV from the host-owned spec.
        transport = temp / "looking-glass-client"
        transport.write_text("#!/bin/sh\n", encoding="utf-8")
        write_proc(proc, 51003, "888", transport)
        resolver.EXPECTED_EXECUTABLES["looking-glass"] = str(transport.resolve())
        write_registry(registry, [{
            "pid": 51003,
            "process_start_ticks": "888",
            "executable": str(transport.resolve()),
            "surface_kind": "looking-glass",
            "domain": "arch-dev-vfio",
            "spec_sha256": digest,
            "registered_by": "hyperlabctl",
        }])

        answer = resolver.stream_answer(
            repo=repo,
            raw=request(12, {"pid": 51003, "app_id": "looking-glass-client",
                             "window_id": "0x4"}).strip(),
            registry_path=registry,
            proc_root=proc,
        )
        require(
            answer["request"] == 12
            and answer["provenance"]["trust"] == "dev"
            and answer["provenance"]["domain"] == "arch-dev-vfio"
            and answer["provenance"]["trust_source"] == "host-owned-vm-spec",
            "a verified registration did not resolve DEV",
        )

        # Profiles are read from specifications, including SERVICES outside
        # the GPU ladder; context/title changes cannot assign an identity.
        for number, profile in enumerate(("clean", "services"), start=20):
            spec.write_text(yaml.safe_dump({
                "name": "arch-dev-vfio", "device_profile": "vfio",
                "network_profile": profile, "looking_glass": True,
            }), encoding="utf-8")
            entry = json.loads(registry.read_text())["entries"][0]
            entry["spec_sha256"] = hashlib.sha256(spec.read_bytes()).hexdigest()
            write_registry(registry, [entry])
            answer = resolver.stream_answer(
                repo=repo,
                raw=request(number, {"pid": 51003, "app_id": "fake-dev",
                                     "title": "DIRTY", "window_id": "0x4"}),
                registry_path=registry, proc_root=proc,
            )
            require(answer["provenance"]["trust"] == profile,
                    f"registered {profile} did not follow the specification")

        spec.write_text(spec.read_text() + "# drift\n", encoding="utf-8")
        answer = resolver.stream_answer(
            repo=repo, raw=request(22, {"pid": 51003}),
            registry_path=registry, proc_root=proc,
        )
        require(answer["provenance"]["reason"] == "registered-domain-spec-drift",
                "stream retained provenance after spec drift")

        # The process exits: its registration can no longer be verified.
        for child in (proc / "51003").iterdir():
            child.unlink()
        (proc / "51003").rmdir()

        answer = resolver.stream_answer(
            repo=repo,
            raw=request(13, {"pid": 51003, "app_id": "looking-glass-client",
                             "window_id": "0x4"}).strip(),
            registry_path=registry,
            proc_root=proc,
        )
        require(
            answer["provenance"]["resolved"] is False
            and answer["provenance"]["reason"]
            == "registered-process-not-verifiable",
            "provenance survived the managed process",
        )


def check_bridge() -> None:
    require(BRIDGE.is_file(), "bridge missing")
    require(
        stat.S_IMODE(BRIDGE.stat().st_mode) == 0o755,
        "bridge is not 0755 in the checkout",
    )

    bridge = text(BRIDGE)

    for marker in (
        "set -euo pipefail",
        "readonly pointer=/etc/hyperlabctl/checkout",
        "readonly python=/usr/bin/python3",
        "[[ $# -eq 1 && $1 == stream ]] || usage",
        '/tools/surface_provenance.py"',
        'exec "${python}" -I -B "${resolver}"',
        "--proc-root /proc",
        '--registry "${runtime_dir}/hyperlab/surface-provenance.json"',
    ):
        require(marker in bridge, f"bridge lost reviewed behavior: {marker}")

    for forbidden in (
        "eval",
        "bash -c",
        "sh -c",
        "sudo",
        "pkexec",
        "virsh",
        "hyprctl",
        "swaymsg",
        "> ",
        "tee",
        "rm ",
    ):
        require(
            forbidden not in bridge,
            f"read-only bridge gained forbidden behavior: {forbidden}",
        )

    tasks = text(TASKS)

    require(
        "    src: privatestack-surface-provenance.sh\n"
        f"    dest: {BRIDGE_PATH}\n"
        "    owner: root\n"
        "    group: root\n"
        '    mode: "0755"\n' in tasks,
        "bridge is not installed root-owned at its reviewed path",
    )

    stage = yaml.safe_load(text(GROUP_VARS))["host_desktop_common_shell_stage"]

    require(
        stage["surface_provenance_bridge"] == BRIDGE_PATH
        and stage["surface_provenance_transport"] == "correlated-stream",
        "shell stage does not declare the provenance bridge",
    )


def check_shell() -> None:
    state = text(QML / "ShellState.qml")
    badge = text(QML / "ProvenanceBadge.qml")
    bar = text(QML / "HyperLabBar.qml")
    diagnostics = text(QML / "DiagnosticsView.qml")
    resolver = text(RESOLVER)

    for marker in (
        f'"{BRIDGE_PATH}"',
        "state.surfaceProvenanceBridge,\n            \"stream\"",
        "stdinEnabled: true",
        "provenanceProcess.write(requestLine + \"\\n\")",
        "parsed.request !== state.provenanceRequest",
        "value.pid !== state.focusPayload.pid",
        "value.guest_metadata_authoritative !== false",
        "value.network_profile !== identity",
        '"host-owned-vm-spec"',
        "state.requestProvenance();",
        "provenanceWatchdog.restart();",
        "state.provenanceStopped();",
    ):
        require(marker in state, f"ShellState provenance wiring lost: {marker}")

    require(
        "No reviewed focused-surface provenance resolver is deployed"
        not in state,
        "ShellState still hardcodes an undeployed resolver",
    )

    # The PID is a lookup key; the title never enters shell state.
    focus = state[state.index("function applyFocusPayload"):]
    focus = focus[:focus.index("\n    }\n")]
    require("title" not in focus, "the focused window title entered state")
    require('"pid":' in focus, "the focused PID is not retained")

    # The shell's reason vocabulary is exactly the resolver's.
    resolver_reasons = set(
        re.findall(r'reason="([a-z-]+)"', resolver)
        + re.findall(r'"reason": "([a-z-]+)"', resolver)
    )
    shell_block = state[state.index("provenanceReasons: ({"):]
    shell_block = shell_block[:shell_block.index("})")]
    shell_reasons = set(re.findall(r'"([a-z-]+)":', shell_block))
    require(
        resolver_reasons == shell_reasons,
        "shell and resolver reason vocabularies differ: "
        f"{sorted(resolver_reasons ^ shell_reasons)}",
    )

    # Presentation reads plain values and owns nothing.
    for name, source in (("ProvenanceBadge.qml", badge),
                         ("DiagnosticsView.qml", diagnostics)):
        for forbidden in ("Process", "surface_provenance", "python",
                          "provenanceProcess", "applyProvenancePayload"):
            require(
                forbidden not in source,
                f"{name} gained provenance authority: {forbidden}",
            )

    # Context and provenance stay separate channels.
    require(
        "context: bar.shellState.focusedSurface" in bar
        and "provenance: bar.shellState.focusedProvenance" in bar,
        "the rail merged focused context and provenance",
    )
    require(
        "focusedProvenance" not in text(QML / "ContextCluster.qml"),
        "the context label began reading provenance",
    )

    shared = "\n".join(text(path) for path in QML.glob("*.qml"))

    for forbidden in ("surface_provenance.py", "/proc/", "python3"):
        require(
            forbidden not in shared,
            f"shared QML bypassed the provenance bridge: {forbidden}",
        )


def check_launcher() -> None:
    source = text(OPEN)

    require(
        '_VIRT_VIEWER = "/usr/bin/virt-viewer"' in source
        and "            argv = [\n                _VIRT_VIEWER," in source,
        "registered console no longer execs the reviewed absolute viewer",
    )

    run = source[source.index("    def run(self, args, ctx):"):]
    register = run.index("_register_surface_provenance(")
    execv = run.index("os.execv(executable")

    require(
        register < execv,
        "managed surfaces must register before exec, in the same process",
    )


def main() -> int:
    require(os.name == "posix", "contract requires POSIX /proc semantics")

    check_stream()
    check_bridge()
    check_shell()
    check_launcher()

    print("HyperLab surface provenance live binding contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
