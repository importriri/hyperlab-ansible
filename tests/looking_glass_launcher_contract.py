#!/usr/bin/env python3
"""Looking Glass launch surfaces must resolve to the managed patched client."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPEN = ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py"
REGISTRY = ROOT / "tools/hyperlabctl/hyperlabctl/registry.py"
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
LG_TASKS = ROOT / "roles/looking_glass/tasks/main.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    opener = OPEN.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    manager = MANAGER.read_text(encoding="utf-8")
    tasks = LG_TASKS.read_text(encoding="utf-8")

    require(
        '_LOOKING_GLASS_CLIENT = "/usr/local/bin/looking-glass-client"' in opener,
        "Looking Glass launcher does not pin the role-owned client path",
    )
    require(
        'def _spice_socket_for_domain(domain):' in opener
        and '"domdisplay"' in opener
        and '"--type"' in opener
        and '"spice"' in opener
        and 'prefix = "spice+unix://"' in opener
        and '"refusing non-UNIX SPICE endpoint' in opener,
        "Looking Glass launcher does not resolve and validate the live UNIX SPICE endpoint",
    )
    require(
        'spice_socket = _spice_socket_for_domain(args.domain)' in opener
        and '"app:shmFile=/dev/kvmfr0",' in opener
        and '"spice:host=%s" % spice_socket,' in opener
        and '"spice:port=0",' in opener
        and '"spice:input=yes",' in opener
        and '"input:captureOnly=yes",' in opener
        and '"input:releaseKeysOnFocusLoss=yes",' in opener,
        "Looking Glass open action does not enforce the reviewed private-input launch contract",
    )
    require(
        '"looking-glass-client",\n                "-F"' not in opener,
        "Looking Glass open action still resolves the client through PATH",
    )

    require(
        '"id": "vm.looking-glass"' in registry
        and '"command": ["hyperlabctl", "open", "looking-glass", "{domain}"]'
        in registry,
        "Looking Glass registry action does not converge on the authoritative opener",
    )

    require(
        manager.count('self._vm_action("vm.looking-glass"') >= 4,
        "Control Center Looking Glass surfaces do not converge on one action id",
    )
    require(
        "looking-glass-client" not in manager,
        "Control Center bypasses the authoritative Looking Glass action",
    )

    require(
        "cmd: make install" in tasks
        and "input_patch_sha256: {{ looking_glass_input_patch_sha256 }}" in tasks
        and 'dest: "{{ looking_glass_stamp }}"' in tasks,
        "Looking Glass role no longer owns the patched client provenance",
    )

    print("Looking Glass launcher ownership contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
