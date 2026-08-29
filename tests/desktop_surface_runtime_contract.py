#!/usr/bin/env python3
"""Contract for VM spec discovery and desktop surface runtime behaviour."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"desktop surface runtime contract: {message}"
        )


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def real_yaml_files(directory: Path) -> set[str]:
    if not directory.exists():
        return set()

    return {
        path.relative_to(ROOT).as_posix()
        for path in directory.glob("*.yml")
        if path.is_file() and not path.is_symlink()
    }


def main() -> int:
    compose = read(
        "tools/hyperlabctl/hyperlabctl/commands/compose.py"
    )

    require(
        "from ..registry import target_choices" in compose,
        "compose list does not use the authoritative target registry",
    )
    require(
        'target_choices("spec", ctx.config.repo_root)' in compose,
        "compose list does not enumerate every valid spec target",
    )
    require(
        "generated_specs(" not in compose,
        "compose list still enumerates generated specs only",
    )

    expected = real_yaml_files(ROOT / "vm-specs")
    expected |= real_yaml_files(ROOT / "vm-specs/.generated")

    binary = ROOT / "tools/hyperlabctl/bin/hyperlabctl"
    result = subprocess.run(
        [str(binary), "--json", "compose", "list"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    require(
        result.returncode == 0,
        "compose list failed: "
        + (result.stderr.strip() or result.stdout.strip()),
    )

    rows = json.loads(result.stdout)
    actual = {
        str(row.get("path"))
        for row in rows
        if isinstance(row, dict)
    }

    require(
        actual == expected,
        "compose list differs from checked-in/generated specs: "
        f"expected={sorted(expected)!r} actual={sorted(actual)!r}",
    )

    manager = read(
        "roles/host_desktop_sway/files/"
        "privatestack-hyperlab-domains.py"
    )

    require(
        "notify::is-active" not in manager
        and "def _on_active_changed(" not in manager,
        "known-bad Layer Shell focus-loss watcher returned",
    )
    require(
        "class HyperlabBackdropWindow" not in manager
        and "backdrop.set_visible(True)" not in manager
        and "backdrop.present()" not in manager,
        "surface routing still maps a second dismissal surface",
    )
    require(
        "root = Gtk.Overlay()" in manager
        and "root.set_child(catcher)" in manager
        and "root.add_overlay(panel)" in manager,
        "single-surface dismissal layout is missing",
    )
    require(
        "LayerShell.Edge.RIGHT" in manager
        and "LayerShell.Edge.BOTTOM" in manager
        and "LayerShell.set_margin(self, LayerShell.Edge.TOP, 0)"
        in manager,
        "cockpit surface does not cover the usable output",
    )
    require(
        "panel.set_size_request(500, 560)" in manager
        and "panel.set_halign(Gtk.Align.START)" in manager
        and "panel.set_margin_top(0)" in manager
        and "panel.set_margin_start(0)" in manager,
        "drawer geometry changed",
    )
    require(
        "panel.set_size_request(1180, 760)" in manager
        and "panel.set_halign(Gtk.Align.CENTER)" in manager
        and "panel.set_margin_top(40)" in manager,
        "Control Center geometry changed",
    )
    require(
        'Path("/etc/hyperlabctl/checkout")' in manager,
        "terminal operations do not read the authoritative checkout pointer",
    )
    require(
        "subprocess.call(argv, cwd=checkout)" in manager,
        "terminal lifecycle operations do not execute from the checkout",
    )

    for row in rows:
        require(
            isinstance(row.get("image"), dict),
            "compose list row is missing image metadata: "
            + str(row.get("path")),
        )
        require(
            row["image"].get("id")
            == (row.get("spec") or {}).get("image"),
            "compose list image metadata differs from its spec: "
            + str(row.get("path")),
        )

    sway = read("roles/host_desktop_sway/files/sway.config")
    mod_f4 = (
        "bindsym $mod+F4 exec "
        "/usr/local/bin/privatestack-hyperlab-domains "
        "--surface overlay --section vms"
    )

    require(
        sway.count(mod_f4) == 1,
        "Mod+F4 must open Control Center on Machines exactly once",
    )
    require(
        "bindsym $mod+F4 exec $hyperdomains" not in sway,
        "Mod+F4 still routes to the compact drawer",
    )

    print("HyperLab desktop surface runtime contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
