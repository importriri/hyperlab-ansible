#!/usr/bin/env python3
"""Regression contract for managed SSH focused-surface provenance."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HYPERLABCTL = ROOT / "tools/hyperlabctl"

sys.path.insert(0, str(HYPERLABCTL))

from hyperlabctl import surface_registry  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab managed SSH provenance contract: " + message
        )


def load_resolver():
    path = ROOT / "tools/surface_provenance.py"
    spec = importlib.util.spec_from_file_location(
        "hyperlab_surface_provenance_ssh_contract",
        path,
    )
    require(spec is not None and spec.loader is not None,
            "cannot load surface provenance resolver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_source_binding() -> None:
    source = (
        ROOT
        / "tools/hyperlabctl/hyperlabctl/commands/open.py"
    ).read_text(encoding="utf-8")

    marker = 'elif args.open_action == "ssh":'
    start = source.find(marker)
    require(start >= 0, "SSH open branch is missing")

    end = source.find("\n        else:", start)
    require(end > start, "cannot delimit SSH open branch")

    branch = source[start:end]

    require(
        'managed_surface_kind = "ssh"' in branch,
        "SSH launch does not declare its managed surface kind",
    )
    require(
        "managed_surface_domain = args.domain" in branch,
        "SSH launch does not bind provenance to its domain",
    )
    require(
        '_FOOT = "/usr/bin/foot"' in source,
        "SSH launcher does not pin Foot to exact /usr/bin/foot",
    )
    require(
        "_FOOT," in branch
        and '"--app-id=hyperlab-managed-ssh"' in branch,
        "SSH Foot launch boundary changed unexpectedly",
    )
    require(
        '"foot"' not in branch,
        "SSH launch fell back to PATH-resolved Foot",
    )


def check_registry_boundary() -> None:
    require(
        surface_registry.EXPECTED_EXECUTABLES.get("ssh")
        == "/usr/bin/foot",
        "registry does not bind SSH to exact /usr/bin/foot",
    )

    try:
        surface_registry.register_managed_surface(
            spec_path=Path("/does/not/matter.yml"),
            domain="arch-dev-vfio",
            surface_kind="ssh",
            executable="/usr/bin/ssh",
        )
    except surface_registry.Unavailable as exc:
        require(
            "reviewed path" in str(exc),
            "wrong SSH surface executable failed for an unexpected reason",
        )
    else:
        raise SystemExit(
            "HyperLab managed SSH provenance contract: "
            "registry accepted /usr/bin/ssh as the graphical surface"
        )


def check_resolver() -> None:
    resolver = load_resolver()

    require(
        "ssh" in resolver.MANAGED_SURFACE_KINDS,
        "resolver does not accept registered SSH surfaces",
    )
    require(
        resolver.EXPECTED_EXECUTABLES.get("ssh") == "/usr/bin/foot",
        "resolver SSH executable is not exact /usr/bin/foot",
    )

    digest = "a" * 64
    pid = 51077
    domain = "arch-dev-vfio"

    entry = {
        "pid": pid,
        "process_start_ticks": "777",
        "executable": "/usr/bin/foot",
        "surface_kind": "ssh",
        "domain": domain,
        "spec_sha256": digest,
        "registered_by": "hyperlabctl",
    }

    registry = {
        "version": 1,
        "entries": [entry],
    }

    surface = {
        "pid": pid,
        "app_id": "hyperlab-managed-ssh",
        "window_id": "0xabc",
        "title": "SSH · arch-dev-vfio",
    }

    originals = {
        "proc_start_ticks": resolver.proc_start_ticks,
        "proc_executable": resolver.proc_executable,
        "spec_for_domain": resolver.spec_for_domain,
        "sha256": resolver.sha256,
    }

    try:
        resolver.proc_start_ticks = lambda proc_root, observed_pid: "777"
        resolver.proc_executable = (
            lambda proc_root, observed_pid: "/usr/bin/foot"
        )
        resolver.spec_for_domain = (
            lambda repo, observed_domain: (
                Path("/reviewed/arch-dev-vfio.yml"),
                {
                    "name": observed_domain,
                    "network_profile": "dev",
                },
            )
        )
        resolver.sha256 = lambda path: digest

        answer = resolver.resolve(
            repo=ROOT,
            surface=surface,
            registry=registry,
            proc_root=Path("/proc-fixture"),
        )

        require(answer.get("resolved") is True,
                "registered SSH surface did not resolve")
        require(answer.get("trust") == "dev",
                "registered SSH did not resolve DEV")
        require(
            answer.get("trust_source") == "host-owned-vm-spec",
            "SSH trust did not come from the host-owned VM spec",
        )
        require(answer.get("domain") == domain,
                "SSH provenance lost its domain")
        require(answer.get("surface_kind") == "ssh",
                "SSH provenance lost its surface kind")

        resolver.proc_executable = (
            lambda proc_root, observed_pid: "/usr/bin/ssh"
        )

        wrong_executable = resolver.resolve(
            repo=ROOT,
            surface=surface,
            registry=registry,
            proc_root=Path("/proc-fixture"),
        )

        require(
            wrong_executable.get("resolved") is False
            and wrong_executable.get("trust") is None
            and wrong_executable.get("reason")
            == "registered-executable-mismatch",
            "wrong executable did not fail closed",
        )

        # A title/app-id alone must never manufacture DEV.
        unregistered = resolver.resolve(
            repo=ROOT,
            surface=surface,
            registry={"version": 1, "entries": []},
            proc_root=Path("/proc-fixture"),
        )

        require(
            unregistered.get("resolved") is False
            and unregistered.get("trust") is None
            and unregistered.get("reason")
            == "managed-surface-not-registered",
            "unregistered managed SSH did not fail closed",
        )

        without_pid = resolver.resolve(
            repo=ROOT,
            surface={
                **surface,
                "pid": None,
            },
            registry={"version": 1, "entries": []},
            proc_root=Path("/proc-fixture"),
        )

        require(
            without_pid.get("resolved") is False
            and without_pid.get("trust") is None
            and without_pid.get("reason")
            == "managed-surface-without-pid",
            "managed SSH without PID did not fail closed",
        )

    finally:
        for name, value in originals.items():
            setattr(resolver, name, value)



def check_qml_presentation_boundary() -> None:
    shell = (
        ROOT
        / "roles/host_desktop_common/files/quickshell/"
          "hyperlab/ShellState.qml"
    ).read_text(encoding="utf-8")

    require(
        '["looking-glass", "spice-console", "ssh"]'
        '.indexOf(value.surface_kind) < 0'
        in shell,
        "ShellState rejects the reviewed SSH managed-surface kind",
    )

    require(
        'value.trust_source !== "host-owned-vm-spec"'
        in shell,
        "ShellState lost host-owned VM spec authority validation",
    )

    require(
        'code !== "managed-surface-resolved"'
        in shell,
        "ShellState lost managed-surface reason validation",
    )

def main() -> int:
    check_source_binding()
    check_registry_boundary()
    check_resolver()
    check_qml_presentation_boundary()
    print("MANAGED_SSH_PROVENANCE_CONTRACT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
