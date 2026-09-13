#!/usr/bin/env python3
"""Contract for host compositor adapter primitives and palette rendering."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = (
    ROOT
    / "roles/host_desktop_hyprland/files"
    / "privatestack-compositor-adapter.sh"
)
PALETTE_SOURCE = ROOT / "tools/palette/palette.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"host Hyprland adapter contract: {message}"
        )


def fake_command(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
{
    printf '%s' "$(basename "$0")"
    for argument in "$@"; do
        printf '|%s' "$argument"
    done
    printf '\\n'
} >>"${HYPERLAB_ADAPTER_LOG:?}"
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def run_adapter(
    backend: str,
    arguments: list[str],
    bin_dir: Path,
    log: Path,
) -> tuple[subprocess.CompletedProcess[str], str]:
    log.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["HYPERLAB_COMPOSITOR_BACKEND"] = backend
    env["HYPERLAB_ADAPTER_LOG"] = str(log)

    result = subprocess.run(
        [str(ADAPTER), *arguments],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )

    return result, log.read_text(encoding="utf-8")


def expect_call(
    backend: str,
    arguments: list[str],
    expected: str,
    bin_dir: Path,
    log: Path,
) -> None:
    result, recorded = run_adapter(
        backend,
        arguments,
        bin_dir,
        log,
    )

    require(
        result.returncode == 0,
        (
            f"{backend} {arguments!r} returned "
            f"{result.returncode}: {result.stderr}"
        ),
    )
    require(
        recorded == expected + "\n",
        (
            f"{backend} {arguments!r} emitted "
            f"{recorded!r}, expected {expected!r}"
        ),
    )


def verify_fake_backends() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-adapter-contract-"
    ) as temporary:
        root = Path(temporary)
        bin_dir = root / "bin"
        bin_dir.mkdir()

        fake_command(bin_dir / "swaymsg")
        fake_command(bin_dir / "hyprctl")

        log = root / "commands.log"
        wallpaper = root / "wallpaper.png"
        wallpaper.write_bytes(b"static-contract-wallpaper")

        expect_call(
            "sway",
            ["keyboard-set", "layout-x", "2"],
            "swaymsg|-q|input|type:keyboard|xkb_layout|layout-x",
            bin_dir,
            log,
        )
        expect_call(
            "hyprland",
            ["keyboard-set", "layout-x", "2"],
            "hyprctl|switchxkblayout|all|2",
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["wallpaper-set", str(wallpaper)],
            (
                "swaymsg|-q|output|*|bg|"
                f"{wallpaper}|fill"
            ),
            bin_dir,
            log,
        )
        expect_call(
            "hyprland",
            ["wallpaper-set", str(wallpaper)],
            (
                "hyprctl|hyprpaper|wallpaper|"
                f", {wallpaper}, cover"
            ),
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["reload"],
            "swaymsg|-q|reload",
            bin_dir,
            log,
        )
        expect_call(
            "hyprland",
            ["reload"],
            "hyprctl|reload",
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["fullscreen-toggle"],
            "swaymsg|-q|fullscreen toggle",
            bin_dir,
            log,
        )
        expect_call(
            "hyprland",
            ["fullscreen-toggle"],
            (
                "hyprctl|dispatch|"
                'hl.dsp.window.fullscreen({ action = "toggle", '
                'mode = "fullscreen" })'
            ),
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["opacity-set", "0.82"],
            "swaymsg|-q|opacity set 0.82",
            bin_dir,
            log,
        )
        expect_call(
            "hyprland",
            ["opacity-set", "0.82"],
            (
                "hyprctl|dispatch|"
                'hl.dsp.window.set_prop({ prop = "opacity", '
                'value = "0.82" })'
            ),
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["dpms", "disable"],
            "swaymsg|-q|output|*|dpms|off",
            bin_dir,
            log,
        )
        expect_call(
            "hyprland",
            ["dpms", "disable"],
            (
                "hyprctl|dispatch|"
                'hl.dsp.dpms({ action = "disable" })'
            ),
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["native-bar", "hide"],
            "swaymsg|bar|mode|invisible|bar-0",
            bin_dir,
            log,
        )

        result, recorded = run_adapter(
            "hyprland",
            ["native-bar", "hide"],
            bin_dir,
            log,
        )
        require(
            result.returncode == 0,
            "Hyprland native-bar no-op failed",
        )
        require(
            recorded == "",
            "Hyprland native-bar must not invoke Sway IPC",
        )


def verify_policy_boundary() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    for forbidden in (
        '"green"',
        '"violet"',
        '"blue"',
        '"red"',
        '"clean"',
        '"dirty"',
        '"dev"',
        '"lab"',
        '"services"',
        '"it"',
        '"us"',
        '"ara"',
        "dom_clean",
        "dom_dirty",
        "gpu_trust",
    ):
        require(
            forbidden not in source,
            f"adapter contains policy literal {forbidden}",
        )

    for marker in (
        "HYPERLAB_COMPOSITOR_BACKEND",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "SWAYSOCK",
        "switchxkblayout",
        "hyprpaper",
        "hl.dsp.window.fullscreen",
        "hl.dsp.window.set_prop",
        "hl.dsp.dpms",
    ):
        require(
            marker in source,
            f"adapter primitive missing: {marker}",
        )


def verify_palette_modules() -> None:
    document = yaml.safe_load(
        PALETTE_SOURCE.read_text(encoding="utf-8")
    )
    domains = document["domains"]

    surface_tokens = (
        "base",
        "mantle",
        "surface",
        "overlay",
        "text",
        "subtext",
        "accent",
        "accent2",
        "ok",
        "warn",
        "bad",
        "dom_clean",
        "dom_dev",
        "dom_lab",
        "dom_dirty",
        "dom_services",
    )

    for variant, values in document["variants"].items():
        palette = dict(values)
        palette.update(domains)

        module = (
            ROOT
            / "roles/host_desktop_sway/files/palette"
            / variant
            / "hyperlab-palette-hyprland.lua"
        )

        require(
            module.is_file(),
            f"generated Hyprland palette missing: {variant}",
        )

        content = module.read_text(encoding="utf-8")

        require(
            "Generated by render_palette.py; do not edit by hand."
            in content,
            f"generated banner missing: {variant}",
        )

        for token in surface_tokens:
            require(
                f'{token} = "{palette[token]}"' in content,
                f"{variant} Hyprland token drift: {token}",
            )

        accent = palette["accent"].lstrip("#")
        overlay = palette["overlay"].lstrip("#")
        bad = palette["bad"].lstrip("#")

        require(
            f'active_border = "rgba({accent}ff)"' in content,
            f"{variant} active border drift",
        )
        require(
            f'inactive_border = "rgba({overlay}ff)"' in content,
            f"{variant} inactive border drift",
        )
        require(
            f'urgent_border = "rgba({bad}ff)"' in content,
            f"{variant} urgent border drift",
        )


def main() -> int:
    require(
        ADAPTER.is_file(),
        "adapter primitive is missing",
    )
    require(
        os.access(ADAPTER, os.X_OK),
        "adapter primitive is not executable",
    )

    verify_policy_boundary()
    verify_palette_modules()
    verify_fake_backends()

    print(
        "HyperLab host Hyprland adapter primitive contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
