#!/usr/bin/env python3
"""Host-independent contracts for read-only M9 gate probes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
os.environ["PRIVATESTACK_BOOTSTRAP_STORAGE_TEST"] = "1"
import sys

sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from release_acceptance import AcceptanceError, load_yaml  # noqa: E402
from release_acceptance_contract import REVIEWED_EVIDENCE  # noqa: E402
from release_probe import build_payload, hash_regular_file, storage_payload  # noqa: E402

MANIFEST = ROOT / "release/acceptance.v2.yml"
PROBE = ROOT / "tools/release_probe.py"
BOOLEAN_TEXT = ("true", "false", "yes", "no", "0", "1")


def contract(topology: str) -> dict[str, object]:
    dedicated = topology == "dedicated-disk"
    return {
        "schema_version": 1,
        "vm_store": {
            "topology": topology,
            "mountpoint": "/var/lib/libvirt/images",
            "mapper": "/dev/mapper/cryptvm" if dedicated else "/dev/mapper/cryptroot",
            "fstype": "btrfs",
            "subvolume": None if dedicated else "@vm",
            "require_nocow": True,
            "root_partlabel": "ARCH_ROOT",
            "vm_partlabel": "ARCH_VM" if dedicated else None,
        },
    }


def observation(source: str, fsroot: str, target: str = "/var/lib/libvirt/images") -> dict[str, object]:
    return {
        "filesystems": [
            {
                "target": target,
                "source": source,
                "fstype": "btrfs",
                "fsroot": fsroot,
                "options": "rw,noatime",
            }
        ]
    }


def write_contract(path: Path, topology: str) -> None:
    path.write_text(yaml.safe_dump(contract(topology), sort_keys=False), encoding="utf-8")
    path.chmod(0o644)


def text_values(gate_id: str, *, without: str = "") -> list[str]:
    """--value arguments for every hash and descriptive field of a gate."""
    classes = REVIEWED_EVIDENCE[gate_id]
    values = [
        f"{field}={hashlib.sha256(field.encode()).hexdigest()}"
        for field in classes["hashes"]
    ]
    values.extend(f"{field}=reviewed-{field}" for field in classes["descriptive"])
    return [value for value in values if value.split("=", 1)[0] != without]


def payload_refused(
    message: str,
    gate_id: str,
    values: list[str],
    true_fields: list[str],
) -> None:
    try:
        build_payload(load_yaml(MANIFEST), gate_id, values, true_fields, [], [])
    except AcceptanceError as exc:
        assert message in str(exc), f"expected {message!r}, got {exc}"
    else:
        raise AssertionError(f"accepted, expected refusal: {message}")


def probe_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROBE), "--manifest", str(MANIFEST), "payload", *arguments],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
    )


def test_storage_probe_accepts_both_reviewed_shapes() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "contract.yml"
        write_contract(path, "single-disk")
        single = storage_payload(
            path,
            Path("/var/lib/libvirt/images"),
            Path("/var/lib/libvirt/images/hyperlab"),
            observation("/dev/mapper/cryptroot[/@vm]", "/@vm"),
            observation("/dev/mapper/cryptroot[/@vm]", "/@vm"),
            "---------------C------ /var/lib/libvirt/images\n",
        )
        assert single["topology"] == "single-disk"
        assert single["mapper"] == "/dev/mapper/cryptroot"
        assert single["hyperlab_device_match"] is True
        assert len(single["contract_sha256"]) == 64

        write_contract(path, "dedicated-disk")
        dedicated = storage_payload(
            path,
            Path("/var/lib/libvirt/images"),
            Path("/var/lib/libvirt/images/hyperlab"),
            observation("/dev/mapper/cryptvm", "/"),
            observation("/dev/mapper/cryptvm", "/"),
            "---------------C------ /var/lib/libvirt/images\n",
        )
        assert dedicated["topology"] == "dedicated-disk"
        assert dedicated["fsroot"] == "/"


def test_storage_probe_refuses_wrong_device_and_missing_nocow() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "contract.yml"
        write_contract(path, "dedicated-disk")
        cases = [
            (
                observation("/dev/mapper/cryptroot[/@vm]", "/@vm"),
                "---------------C------ /var/lib/libvirt/images\n",
                "not backed by the verified mapper",
            ),
            (
                observation("/dev/mapper/cryptvm", "/"),
                "---------------------- /var/lib/libvirt/images\n",
                "lacks inherited NOCOW",
            ),
        ]
        for hyperlab, attributes, message in cases:
            try:
                storage_payload(
                    path,
                    Path("/var/lib/libvirt/images"),
                    Path("/var/lib/libvirt/images/hyperlab"),
                    observation("/dev/mapper/cryptvm", "/"),
                    hyperlab,
                    attributes,
                )
            except (AcceptanceError, ValueError) as exc:
                assert message in str(exc)
            else:
                raise AssertionError("storage drift was accepted")


def test_payload_hashes_files_and_types_reviewed_booleans() -> None:
    manifest = load_yaml(MANIFEST)
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "dry-run.log"
        log.write_text("reviewed dry run\n", encoding="utf-8")
        payload = build_payload(
            manifest,
            "bootstrap-dry-run",
            ["selected_primary_disk=/dev/nvme0n1", "selected_vm_disk=none"],
            ["no_writes_observed"],
            [],
            [f"dry_run_sha256={log}"],
        )
        assert payload["selected_primary_disk"] == "/dev/nvme0n1"
        assert payload["no_writes_observed"] is True
        assert len(payload["dry_run_sha256"]) == 64

        try:
            build_payload(
                manifest,
                "bootstrap-dry-run",
                [
                    "selected_primary_disk=/dev/nvme0n1",
                    "selected_vm_disk=none",
                    "no_writes_observed=true",
                ],
                [],
                [],
                [f"dry_run_sha256={log}"],
            )
        except AcceptanceError as exc:
            assert "needs --true or --false" in str(exc)
        else:
            raise AssertionError("boolean text was accepted")


def test_payload_refuses_missing_extra_duplicate_and_symlink_hashes() -> None:
    manifest = load_yaml(MANIFEST)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        log = root / "log"
        log.write_text("evidence\n", encoding="utf-8")
        link = root / "link"
        link.symlink_to(log)
        cases = [
            (
                lambda: build_payload(
                    manifest,
                    "bootstrap-dry-run",
                    ["selected_primary_disk=/dev/nvme0n1"],
                    ["no_writes_observed"],
                    [],
                    [f"dry_run_sha256={log}"],
                ),
                "fields differ",
            ),
            (
                lambda: build_payload(
                    manifest,
                    "bootstrap-dry-run",
                    [
                        "selected_primary_disk=/dev/nvme0n1",
                        "selected_vm_disk=none",
                        "extra_field=value",
                    ],
                    ["no_writes_observed"],
                    [],
                    [f"dry_run_sha256={log}"],
                ),
                "fields differ",
            ),
            (
                lambda: build_payload(
                    manifest,
                    "bootstrap-dry-run",
                    [
                        "selected_primary_disk=/dev/nvme0n1",
                        "selected_primary_disk=/dev/nvme1n1",
                        "selected_vm_disk=none",
                    ],
                    ["no_writes_observed"],
                    [],
                    [f"dry_run_sha256={log}"],
                ),
                "supplied more than once",
            ),
            (lambda: hash_regular_file(link), "regular non-symlink"),
        ]
        for operation, message in cases:
            try:
                operation()
            except AcceptanceError as exc:
                assert message in str(exc)
            else:
                raise AssertionError(f"mutation was accepted: {message}")


def test_publication_gate_hashes_the_bundle_not_its_future_receipt() -> None:
    manifest = load_yaml(MANIFEST)
    gate = next(item for item in manifest["gates"] if item["id"] == "sanitized-publication")
    assert gate["required_evidence"] == [
        "publication_bundle_sha256",
        "no_sensitive_patterns",
        "exact_commit_matrix",
        "known_limits",
    ]
    assert "evidence_receipt_sha256" not in json.dumps(manifest)


def test_payload_types_every_reviewed_boolean_from_its_own_flag() -> None:
    manifest = load_yaml(MANIFEST)
    for gate_id, classes in REVIEWED_EVIDENCE.items():
        values = text_values(gate_id)
        booleans = list(classes["booleans"])
        for field in booleans:
            others = [item for item in booleans if item != field]
            proven = build_payload(manifest, gate_id, values, booleans, [], [])
            assert proven[field] is True, f"--true {field} did not give true"
            failed = build_payload(manifest, gate_id, values, others, [field], [])
            assert failed[field] is False, f"--false {field} did not give false"
            for text in BOOLEAN_TEXT:
                payload_refused(
                    f"boolean field {field} needs --true or --false",
                    gate_id,
                    [*values, f"{field}={text}"],
                    others,
                )
        for field in classes["descriptive"]:
            payload_refused(
                f"field {field} is not a reviewed boolean",
                gate_id,
                text_values(gate_id, without=field),
                [*booleans, field],
            )
    payload_refused(
        "field loopback_spice is not a reviewed boolean",
        "looking-glass",
        text_values("looking-glass"),
        ["spice_socket_private", "loopback_spice"],
    )


def test_probe_command_types_the_private_spice_socket() -> None:
    values = [
        argument
        for value in text_values("looking-glass")
        for argument in ("--value", value)
    ]
    proven = probe_cli("--gate", "looking-glass", *values, "--true", "spice_socket_private")
    assert proven.returncode == 0, proven.stderr
    assert json.loads(proven.stdout)["spice_socket_private"] is True, proven.stdout

    failed = probe_cli("--gate", "looking-glass", *values, "--false", "spice_socket_private")
    assert failed.returncode == 0, failed.stderr
    assert json.loads(failed.stdout)["spice_socket_private"] is False, (
        f"--false spice_socket_private gave {failed.stdout}"
    )

    for text in BOOLEAN_TEXT:
        result = probe_cli(
            "--gate", "looking-glass", *values, "--value", f"spice_socket_private={text}"
        )
        assert result.returncode == 2, f"--value spice_socket_private={text} was accepted"
        assert (
            "boolean field spice_socket_private needs --true or --false" in result.stderr
        ), result.stderr

    retired = probe_cli(
        "--gate",
        "looking-glass",
        *values,
        "--true",
        "spice_socket_private",
        "--true",
        "loopback_spice",
    )
    assert retired.returncode == 2, "--true loopback_spice was accepted"
    assert "field loopback_spice is not a reviewed boolean" in retired.stderr, (
        retired.stderr
    )


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"release probe contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
