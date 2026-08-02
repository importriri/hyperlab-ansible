#!/usr/bin/env python3
"""Host-independent M8 exposure planning and nftables hook contracts."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PLAN = ROOT / "tools/service_plan.py"
EXPOSURE_PLAN = ROOT / "tools/service_exposure_plan.py"
EXPOSURE_APPLY = ROOT / "tools/service_exposure_apply.py"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=stdin, text=True, capture_output=True, check=False)


def service_plan(store: Path) -> dict[str, Any]:
    result = run(
        sys.executable, str(SERVICE_PLAN),
        "--root", str(ROOT),
        "--spec", str(ROOT / "service-specs/svc-jellyfin.yml"),
        "--store", str(store),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def exposure_plan(service: dict[str, Any], routes: list[dict[str, Any]], override: str = "") -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable, str(EXPOSURE_PLAN),
        "--bridge", "virbr-services",
        "--interface-override", override,
        stdin=json.dumps({"service_plan": service, "routes": routes}),
    )


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exposure_entry(interface: str = "enp3s0") -> dict[str, Any]:
    return {
        "comment": "privatestack-service-exposure:svc-jellyfin:tcp:8096",
        "domain": "svc-jellyfin",
        "guest_bridge": "virbr-services",
        "guest_ip": "10.10.5.10",
        "guest_port": 8096,
        "host_port": 8096,
        "lan_interface": interface,
        "protocol": "tcp",
    }


def config(state_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state_dir": str(state_dir),
        "nft_table_family": "ip",
        "nft_table_name": "privatestack_services",
        "libvirt_table_family": "ip",
        "libvirt_table_name": "libvirt_network",
        "libvirt_input_chain": "guest_input",
        "domains": {"svc-jellyfin": [exposure_entry()]},
    }


def test_exposure_plan_and_refusals() -> None:
    with tempfile.TemporaryDirectory() as td:
        service = service_plan(Path(td) / "store")
        result = exposure_plan(service, [{"dst": "default", "dev": "enp3s0"}])
        assert result.returncode == 0, result.stderr
        plan = json.loads(result.stdout)
        assert plan["domains"] == {"svc-jellyfin": [exposure_entry()]}

        ambiguous = exposure_plan(service, [
            {"dst": "default", "dev": "enp3s0"},
            {"dst": "default", "dev": "wlan0"},
        ])
        assert ambiguous.returncode == 2 and "exactly one" in ambiguous.stderr

        selected = exposure_plan(service, [
            {"dst": "default", "dev": "enp3s0"},
            {"dst": "default", "dev": "wlan0"},
        ], "wlan0")
        assert selected.returncode == 0
        assert json.loads(selected.stdout)["domains"]["svc-jellyfin"] == [exposure_entry("wlan0")]

        virtual = exposure_plan(service, [{"dst": "default", "dev": "virbr0"}])
        assert virtual.returncode == 2 and "physical/default-route" in virtual.stderr

        missing = dict(service)
        missing["exposures"] = []
        refused = exposure_plan(missing, [{"dst": "default", "dev": "enp3s0"}])
        assert refused.returncode == 2 and "at least one" in refused.stderr


def test_nft_reconcile_owns_only_marked_rules() -> None:
    module = load_module(EXPOSURE_APPLY, "service_exposure_apply_contract")
    calls: list[tuple[list[str], str | None]] = []
    chain_payload = {"nftables": [
        {"rule": {"handle": 17, "comment": "privatestack-service-exposure:svc-jellyfin:tcp:8096"}},
        {"rule": {"handle": 9, "comment": "libvirt-unrelated"}},
    ]}

    def fake_run(command: list[str], *, stdin: str | None = None, ok: set[int] | None = None) -> subprocess.CompletedProcess[str]:
        calls.append((list(command), stdin))
        if command[1:5] == ["-j", "-a", "list", "chain"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(chain_payload), "")
        if command[1:4] == ["delete", "table", "ip"]:
            return subprocess.CompletedProcess(command, 1, "", "No such file")
        return subprocess.CompletedProcess(command, 0, "", "")

    module.run = fake_run
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        cfg = config(state_dir)
        module.update_marker(cfg, state_dir, "svc-jellyfin", "prepare")
        assert module.reconcile("/usr/bin/nft", cfg, state_dir) == {
            "active_domains": ["svc-jellyfin"], "exposure_count": 1,
        }
        deleted = [command[-1] for command, _ in calls if command[1:3] == ["delete", "rule"]]
        assert deleted == ["17"]
        batches = [stdin for command, stdin in calls if command[1:3] == ["-f", "-"]]
        assert len(batches) == 1
        assert 'iifname "enp3s0" tcp dport 8096 dnat to 10.10.5.10:8096' in batches[0]
        inserts = [command for command, _ in calls if command[1:3] == ["insert", "rule"]]
        assert len(inserts) == 1
        assert inserts[0][-2:] == ["comment", "privatestack-service-exposure:svc-jellyfin:tcp:8096"]

        calls.clear()
        module.update_marker(cfg, state_dir, "svc-jellyfin", "release")
        assert module.reconcile("/usr/bin/nft", cfg, state_dir) == {
            "active_domains": [], "exposure_count": 0,
        }
        assert not any(command[1:3] in (["-f", "-"], ["insert", "rule"]) for command, _ in calls)

        (state_dir / "unknown").write_text("active\n", encoding="ascii")
        try:
            module.active_exposures(cfg, state_dir)
        except module.ExposureError as exc:
            assert "unknown service exposure state marker" in str(exc)
        else:
            raise AssertionError("unknown state marker unexpectedly passed")


def test_config_and_hook_structure() -> None:
    module = load_module(EXPOSURE_APPLY, "service_exposure_apply_config")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "exposures.json"
        path.write_text(json.dumps(config(Path(td) / "state")), encoding="utf-8")
        path.chmod(0o600)
        previous = os.environ.get("PRIVATESTACK_EXPOSURE_TEST")
        os.environ["PRIVATESTACK_EXPOSURE_TEST"] = "1"
        try:
            loaded = module.load_config(path)
            assert loaded["domains"]["svc-jellyfin"][0]["host_port"] == 8096
            loaded["domains"]["svc-jellyfin"][0]["host_port"] = 8920
            path.write_text(json.dumps(loaded), encoding="utf-8")
            try:
                module.load_config(path)
            except module.ExposureError as exc:
                assert "comment does not match" in str(exc)
            else:
                raise AssertionError("mismatched exposure comment unexpectedly passed")
        finally:
            if previous is None:
                os.environ.pop("PRIVATESTACK_EXPOSURE_TEST", None)
            else:
                os.environ["PRIVATESTACK_EXPOSURE_TEST"] = previous

    hook = (ROOT / "roles/service_exposure/files/qemu-hook").read_text()
    tasks = (ROOT / "roles/service_exposure/tasks/main.yml").read_text()
    handlers = (ROOT / "roles/service_exposure/handlers/main.yml").read_text()
    assert hook.startswith("#!/usr/bin/env bash\n")
    assert ">/dev/null" in hook and "set -euo pipefail" in hook
    assert "Install the static qemu.d service exposure hook" in tasks
    assert "Refuse any M8 exposure except Jellyfin HTTP" in tasks
    assert tasks.index("Verify the M7 service registration receipt before exposure") < tasks.index(
        "Install nftables for service exposure"
    )
    assert handlers.index("Read active domains before libvirt hook reload") < handlers.index(
        "Restart libvirt for service exposure hooks"
    )


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"service exposure contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
