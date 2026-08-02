#!/usr/bin/env python3
"""Reconcile reviewed service DNAT and libvirt forward rules from hook state."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

COMMENT_PREFIX = "privatestack-service-exposure:"
DOMAIN_RE = re.compile(r"^svc-[a-z0-9][a-z0-9-]*$")
IFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")
TABLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
IP_RE = re.compile(r"^10\.10\.5\.(?:[1-9]|[1-9][0-9]|2[0-4][0-9]|25[0-4])$")


class ExposureError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExposureError(message)


def regular_safe_file(path: Path) -> None:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "service exposure config must be one regular non-symlink file")
    require(info.st_uid == 0 or os.environ.get("PRIVATESTACK_EXPOSURE_TEST") == "1",
            "service exposure config must be root-owned")
    require(info.st_mode & 0o022 == 0, "service exposure config must not be group/world writable")


def load_config(path: Path) -> dict[str, Any]:
    try:
        regular_safe_file(path)
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExposureError(f"service exposure config does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExposureError(f"service exposure config cannot be read: {exc}") from exc
    require(isinstance(data, dict), "service exposure config root must be a mapping")
    require(data.get("schema_version") == 1, "service exposure config schema_version must be 1")
    domains = data.get("domains")
    require(isinstance(domains, dict), "service exposure domains must be a mapping")
    for domain, exposures in domains.items():
        require(isinstance(domain, str) and DOMAIN_RE.fullmatch(domain) is not None,
                f"invalid service exposure domain {domain!r}")
        require(isinstance(exposures, list) and exposures, f"domain {domain} needs exposure entries")
        for exposure in exposures:
            require(isinstance(exposure, dict), "service exposure entry must be a mapping")
            require(exposure.get("domain") == domain, "service exposure domain entry differs from its key")
            require(exposure.get("protocol") in {"tcp", "udp"}, "unsupported service exposure protocol")
            for key in ("host_port", "guest_port"):
                port = exposure.get(key)
                require(isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535,
                        f"invalid service exposure {key}")
            require(isinstance(exposure.get("lan_interface"), str)
                    and IFACE_RE.fullmatch(exposure["lan_interface"]) is not None,
                    "invalid service exposure LAN interface")
            require(exposure.get("guest_bridge") == "virbr-services",
                    "service exposure bridge must remain virbr-services")
            require(isinstance(exposure.get("guest_ip"), str)
                    and IP_RE.fullmatch(exposure["guest_ip"]) is not None,
                    "service exposure guest IP is invalid")
            expected_comment = (
                f"{COMMENT_PREFIX}{domain}:{exposure['protocol']}:{exposure['host_port']}"
            )
            require(exposure.get("comment") == expected_comment,
                    "service exposure comment does not match its identity")
    for key in ("nft_table_name", "libvirt_table_name", "libvirt_input_chain"):
        require(isinstance(data.get(key), str) and TABLE_RE.fullmatch(data[key]) is not None,
                f"invalid service exposure {key}")
    require(data.get("nft_table_family") == "ip" and data.get("libvirt_table_family") == "ip",
            "M8 service exposure is IPv4-only")
    return data


def run(command: list[str], *, stdin: str | None = None, ok: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, input=stdin, text=True, capture_output=True, check=False)
    allowed = {0} if ok is None else ok
    if result.returncode not in allowed:
        raise ExposureError(
            f"command failed ({result.returncode}): {' '.join(command)}: {result.stderr.strip()}"
        )
    return result


def matching_rule_handles(nft: str, family: str, table: str, chain: str) -> list[int]:
    result = run([nft, "-j", "-a", "list", "chain", family, table, chain])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExposureError(f"nft returned invalid JSON for {table}/{chain}: {exc}") from exc
    require(isinstance(payload, dict) and isinstance(payload.get("nftables"), list),
            "nft chain JSON has an invalid root")
    handles: list[int] = []
    for item in payload["nftables"]:
        if not isinstance(item, dict) or not isinstance(item.get("rule"), dict):
            continue
        rule = item["rule"]
        comment = rule.get("comment")
        handle = rule.get("handle")
        if isinstance(comment, str) and comment.startswith(COMMENT_PREFIX):
            require(isinstance(handle, int), "managed nft rule lacks an integer handle")
            handles.append(handle)
    return sorted(handles, reverse=True)


def delete_managed_forward_rules(nft: str, config: dict[str, Any]) -> None:
    family = config["libvirt_table_family"]
    table = config["libvirt_table_name"]
    chain = config["libvirt_input_chain"]
    for handle in matching_rule_handles(nft, family, table, chain):
        run([nft, "delete", "rule", family, table, chain, "handle", str(handle)])


def delete_owned_table(nft: str, config: dict[str, Any]) -> None:
    run(
        [nft, "delete", "table", config["nft_table_family"], config["nft_table_name"]],
        ok={0, 1},
    )


def active_exposures(config: dict[str, Any], state_dir: Path) -> list[dict[str, Any]]:
    if not state_dir.exists():
        return []
    require(state_dir.is_dir() and not state_dir.is_symlink(),
            "service exposure state root must be a non-symlink directory")
    active: list[dict[str, Any]] = []
    for marker in sorted(state_dir.iterdir()):
        if not marker.is_file() or marker.is_symlink():
            raise ExposureError(f"invalid service exposure state marker: {marker}")
        domain = marker.name
        require(domain in config["domains"], f"unknown service exposure state marker: {domain}")
        active.extend(config["domains"][domain])
    return active


def nft_quote(value: str) -> str:
    require('"' not in value and "\\" not in value and "\n" not in value,
            "unsafe value reached nft rendering")
    return f'"{value}"'


def render_nat_table(config: dict[str, Any], exposures: list[dict[str, Any]]) -> str:
    lines = [
        f"table {config['nft_table_family']} {config['nft_table_name']} {{",
        "  chain prerouting {",
        "    type nat hook prerouting priority dstnat; policy accept;",
    ]
    for exposure in exposures:
        protocol = exposure["protocol"]
        lines.append(
            "    "
            f"iifname {nft_quote(exposure['lan_interface'])} "
            f"{protocol} dport {exposure['host_port']} "
            f"dnat to {exposure['guest_ip']}:{exposure['guest_port']} "
            f"comment {nft_quote(exposure['comment'])}"
        )
    lines.extend(["  }", "}", ""])
    return "\n".join(lines)


def add_forward_rules(nft: str, config: dict[str, Any], exposures: list[dict[str, Any]]) -> None:
    family = config["libvirt_table_family"]
    table = config["libvirt_table_name"]
    chain = config["libvirt_input_chain"]
    for exposure in exposures:
        run([
            nft,
            "insert",
            "rule",
            family,
            table,
            chain,
            "oifname",
            exposure["guest_bridge"],
            "ip",
            "daddr",
            exposure["guest_ip"],
            exposure["protocol"],
            "dport",
            str(exposure["guest_port"]),
            "ct",
            "state",
            "new,established",
            "counter",
            "accept",
            "comment",
            exposure["comment"],
        ])


def reconcile(nft: str, config: dict[str, Any], state_dir: Path) -> dict[str, Any]:
    exposures = active_exposures(config, state_dir)
    delete_managed_forward_rules(nft, config)
    delete_owned_table(nft, config)
    if not exposures:
        return {"active_domains": [], "exposure_count": 0}
    try:
        run([nft, "-f", "-"], stdin=render_nat_table(config, exposures))
        add_forward_rules(nft, config, exposures)
    except ExposureError:
        delete_managed_forward_rules(nft, config)
        delete_owned_table(nft, config)
        raise
    active_domains = sorted({exposure["domain"] for exposure in exposures})
    return {"active_domains": active_domains, "exposure_count": len(exposures)}


def update_marker(config: dict[str, Any], state_dir: Path, domain: str, operation: str) -> None:
    if domain not in config["domains"]:
        return
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    marker = state_dir / domain
    if operation in {"prepare", "start", "started", "reconnect"}:
        marker.write_text("active\n", encoding="ascii")
        os.chmod(marker, 0o600)
    elif operation in {"stopped", "release"}:
        marker.unlink(missing_ok=True)
    elif operation != "reconcile":
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--nft", default="/usr/bin/nft")
    parser.add_argument("--domain", default="-")
    parser.add_argument("--operation", required=True)
    args = parser.parse_args()
    try:
        config = load_config(Path(args.config))
        state_dir = Path(str(config.get("state_dir", "")))
        require(state_dir.is_absolute() and str(state_dir) != "/",
                "service exposure state_dir must be one absolute non-root path")
        update_marker(config, state_dir, args.domain, args.operation)
        result = reconcile(args.nft, config, state_dir)
    except (OSError, ExposureError) as exc:
        print(f"service exposure refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
