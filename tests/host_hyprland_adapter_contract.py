#!/usr/bin/env python3
"""Executable contract for the shared host compositor adapter."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

ADAPTER = (
    ROOT
    / "roles/host_desktop_common/files"
    / "privatestack-compositor-adapter.sh"
)

PALETTE_SOURCE = (
    ROOT
    / "tools/palette/palette.yml"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise SystemExit(
            f"host compositor adapter contract: {message}"
        )


def fake_command(
    path: Path,
    body: str = "",
) -> None:
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

if [[ ${HYPERLAB_FAKE_BACKEND_FAIL:-0} == 1 ]]; then
    exit 42
fi
"""
        + body,
        encoding="utf-8",
    )

    path.chmod(0o755)


def run_adapter(
    backend: str,
    arguments: list[str],
    bin_dir: Path,
    log: Path,
    extra_env: dict[str, str] | None = None,
) -> tuple[
    subprocess.CompletedProcess[str],
    str,
]:
    log.write_text(
        "",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PATH"] = (
        f"{bin_dir}:{env['PATH']}"
    )
    env[
        "HYPERLAB_COMPOSITOR_BACKEND"
    ] = backend
    env[
        "HYPERLAB_ADAPTER_LOG"
    ] = str(log)

    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [
            str(ADAPTER),
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
        timeout=7,
    )

    return (
        result,
        log.read_text(
            encoding="utf-8",
        ),
    )


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
            f"{backend} {arguments!r} "
            f"returned {result.returncode}: "
            f"{result.stderr}"
        ),
    )

    require(
        recorded == expected + "\n",
        (
            f"{backend} {arguments!r} "
            f"emitted {recorded!r}, "
            f"expected {expected!r}"
        ),
    )


def verify_fake_backends() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-adapter-contract-"
    ) as temporary:
        root = Path(temporary)
        bin_dir = root / "bin"
        bin_dir.mkdir()

        fake_command(
            bin_dir / "swaymsg",
            """
if [[ "$*" == "-r -t get_tree" ]]; then
    printf '%s\\n' \
      '{"focused":false,"nodes":[{"focused":true,"id":42,"app_id":"foot"}]}'
fi
""",
        )

        fake_command(
            bin_dir / "hyprctl",
            """
if [[ "${1:-}" == "activewindow" &&
      "${2:-}" == "-j" ]]
then
    printf '%s\\n' \
      '{"address":"0xabc","class":"foot"}'
fi
""",
        )

        fake_command(
            bin_dir / "hyprshutdown"
        )

        log = root / "commands.log"

        wallpaper = root / "wallpaper.png"
        wallpaper.write_bytes(
            b"static-contract-wallpaper"
        )

        order = "zero,one,layout-x"

        expect_call(
            "sway",
            [
                "keyboard-set",
                "layout-x",
                "2",
                order,
            ],
            (
                "swaymsg|-q|input|"
                "type:keyboard|xkb_layout|"
                "layout-x"
            ),
            bin_dir,
            log,
        )

        expect_call(
            "hyprland",
            [
                "keyboard-set",
                "layout-x",
                "2",
                order,
            ],
            (
                "hyprctl|switchxkblayout|"
                "all|2"
            ),
            bin_dir,
            log,
        )

        result, recorded = run_adapter(
            "hyprland",
            [
                "keyboard-set",
                "layout-x",
                "1",
                order,
            ],
            bin_dir,
            log,
        )

        require(
            result.returncode == 2,
            (
                "mismatched keyboard "
                "layout/index was accepted"
            ),
        )

        require(
            recorded == "",
            (
                "mismatched keyboard contract "
                "reached compositor IPC"
            ),
        )

        result, recorded = run_adapter(
            "hyprland",
            [
                "keyboard-set",
                "layout-x",
                "99",
                order,
            ],
            bin_dir,
            log,
        )

        require(
            result.returncode == 2,
            "out-of-range keyboard index was accepted",
        )

        require(
            recorded == "",
            (
                "out-of-range keyboard index "
                "reached compositor IPC"
            ),
        )

        expect_call(
            "sway",
            [
                "wallpaper-set",
                str(wallpaper),
            ],
            (
                "swaymsg|-q|output|*|bg|"
                f"{wallpaper}|fill"
            ),
            bin_dir,
            log,
        )

        expect_call(
            "hyprland",
            [
                "wallpaper-set",
                str(wallpaper),
            ],
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
                "hl.dsp.window.fullscreen"
                '({ action = "toggle", '
                'mode = "fullscreen" })'
            ),
            bin_dir,
            log,
        )

        result, recorded = run_adapter(
            "sway",
            ["focused-window"],
            bin_dir,
            log,
        )

        require(
            result.returncode == 0,
            result.stderr,
        )

        require(
            result.stdout == "42\tfoot\n",
            "bad Sway focused-window result",
        )

        require(
            recorded
            == "swaymsg|-r|-t|get_tree\n",
            "bad Sway focused-window IPC",
        )

        result, recorded = run_adapter(
            "hyprland",
            ["focused-window"],
            bin_dir,
            log,
        )

        require(
            result.returncode == 0,
            result.stderr,
        )

        require(
            result.stdout == "0xabc\tfoot\n",
            "bad Hyprland focused-window result",
        )

        require(
            recorded
            == "hyprctl|activewindow|-j\n",
            "bad Hyprland focused-window IPC",
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
                "hl.dsp.window.set_prop"
                '({ prop = "opacity", '
                'value = "0.82" })'
            ),
            bin_dir,
            log,
        )

        result, recorded = run_adapter(
            "sway",
            ["opacity-set", "1.20"],
            bin_dir,
            log,
        )

        require(
            result.returncode == 2,
            "invalid opacity was accepted",
        )

        require(
            recorded == "",
            (
                "invalid opacity reached "
                "compositor IPC"
            ),
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
                "hl.dsp.dpms"
                '({ action = "disable" })'
            ),
            bin_dir,
            log,
        )

        expect_call(
            "sway",
            ["native-bar", "hide"],
            (
                "swaymsg|bar|mode|"
                "invisible|bar-0"
            ),
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
            (
                "Hyprland native-bar must not "
                "invoke Sway IPC"
            ),
        )

        expect_call(
            "sway",
            ["session-exit"],
            "swaymsg|exit",
            bin_dir,
            log,
        )

        expect_call(
            "hyprland",
            ["session-exit"],
            "hyprshutdown",
            bin_dir,
            log,
        )

        result, recorded = run_adapter(
            "sway",
            ["reload"],
            bin_dir,
            log,
            {
                "HYPERLAB_FAKE_BACKEND_FAIL": "1",
            },
        )

        require(
            result.returncode == 42,
            (
                "backend failure was not "
                "propagated"
            ),
        )

        require(
            recorded == "swaymsg|-q|reload\n",
            (
                "backend failure test did not "
                "reach expected IPC"
            ),
        )


def verify_policy_boundary() -> None:
    source = ADAPTER.read_text(
        encoding="utf-8"
    )

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
            (
                "adapter contains policy literal "
                f"{forbidden}"
            ),
        )

    for marker in (
        "HYPERLAB_COMPOSITOR_BACKEND",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "SWAYSOCK",
        "keyboard layout/index mismatch",
        "switchxkblayout",
        "hyprpaper",
        "focused-window",
        "activewindow",
        "hl.dsp.window.fullscreen",
        "hl.dsp.window.set_prop",
        "hl.dsp.dpms",
        "hyprshutdown",
        "timeout",
    ):
        require(
            marker in source,
            f"adapter primitive missing: {marker}",
        )


def verify_palette_modules() -> None:
    document = yaml.safe_load(
        PALETTE_SOURCE.read_text(
            encoding="utf-8"
        )
    )

    domains = document["domains"]

    tokens = (
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

    for variant, values in (
        document["variants"].items()
    ):
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
            (
                "Hyprland palette missing: "
                f"{variant}"
            ),
        )

        content = module.read_text(
            encoding="utf-8"
        )

        lines = content.splitlines()

        require(
            "\\n" not in content,
            (
                f"{variant} contains literal "
                "newline escapes"
            ),
        )

        require(
            len(lines) >= 20
            and lines[1] == "return {"
            and lines[-1] == "}",
            (
                f"{variant} is not a real "
                "Lua return-table module"
            ),
        )

        for token in tokens:
            require(
                (
                    f'{token} = '
                    f'"{palette[token]}"'
                )
                in content,
                (
                    f"{variant} token drift: "
                    f"{token}"
                ),
            )


def main() -> int:
    require(
        ADAPTER.is_file(),
        "shared adapter missing",
    )

    require(
        os.access(
            ADAPTER,
            os.X_OK,
        ),
        "shared adapter is not executable",
    )

    verify_policy_boundary()
    verify_palette_modules()
    verify_fake_backends()

    print(
        "HyperLab shared compositor "
        "adapter contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
