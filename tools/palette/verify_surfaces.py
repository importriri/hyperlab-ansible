#!/usr/bin/env python3
"""Verify palette fragments and every tokenised desktop surface."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_palette import SURFACE_TOKENS  # noqa: E402


REPO = Path(__file__).resolve().parent.parent.parent
SURFACES = REPO / "roles/host_desktop_sway/files"


def allowed_literals() -> dict[str, str]:
    path = Path(__file__).parent / "derivate.txt"

    if not path.is_file():
        return {}

    out: dict[str, str] = {}

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = line.strip()

        if (
            not line
            or line.startswith("#  ")
            or line.startswith("# ")
        ):
            continue

        if line.startswith("#") and len(line) >= 7:
            parts = line.split(None, 1)

            if len(parts[0]) == 7:
                out[parts[0].lower()] = (
                    parts[1] if len(parts) > 1 else ""
                )

    return out


PASSED: list[str] = []
FAILED: list[str] = []


def check(
    name: str,
    condition: bool,
    detail: str = "",
) -> None:
    (PASSED if condition else FAILED).append(name)

    print(
        f"  {'ok  ' if condition else 'FAIL'} {name}"
        f"{'  — ' + detail if detail and not condition else ''}"
    )


def verify_hyprland_module(
    fragments: Path,
    variant: str,
) -> None:
    module = (
        fragments
        / variant
        / "hyperlab-palette-hyprland.lua"
    )

    check(
        f"{variant}: Hyprland Lua exists",
        module.is_file(),
    )

    if not module.is_file():
        return

    source = module.read_text(encoding="utf-8")
    lines = source.splitlines()

    check(
        f"{variant}: Hyprland Lua has real newlines",
        "\\n" not in source and len(lines) >= 20,
        "literal backslash-n or collapsed module",
    )

    check(
        f"{variant}: Hyprland Lua returns a table",
        len(lines) >= 3
        and lines[1] == "return {"
        and lines[-1] == "}",
        "return-table structure missing",
    )

    keys = set(
        re.findall(
            r'(?m)^\s+([a-z_][a-z0-9_]*)\s*=\s*"[^"]+",$',
            source,
        )
    )

    expected = set(SURFACE_TOKENS) | {
        "active_border",
        "inactive_border",
        "urgent_border",
    }

    check(
        f"{variant}: Hyprland Lua table has every token",
        keys == expected,
        (
            f"missing {sorted(expected - keys)}, "
            f"unexpected {sorted(keys - expected)}"
        ),
    )


def main(argv: list[str]) -> int:
    fragments = (
        Path(argv[1])
        if len(argv) > 1
        else SURFACES / "palette"
    )

    known = {
        f"hl_{token}"
        for token in SURFACE_TOKENS
    }

    print("=== fragments define every token")

    variants = sorted(
        path.name
        for path in fragments.iterdir()
        if path.is_dir()
    )

    check(
        "at least two variants",
        len(variants) >= 2,
        f"found {variants}",
    )

    for variant in variants:
        gtk = (
            fragments
            / variant
            / "hyperlab-palette-gtk.css"
        )

        defined = set(
            re.findall(
                r"@define-color\s+(hl_\w+)",
                gtk.read_text(encoding="utf-8"),
            )
        )

        check(
            f"{variant}: {len(SURFACE_TOKENS)} tokens defined",
            defined == known,
            f"missing {sorted(known - defined)}",
        )

        verify_hyprland_module(
            fragments,
            variant,
        )

    shapes = {
        re.sub(
            r"#[0-9a-fA-F]{6}",
            "X",
            (
                fragments
                / variant
                / "hyperlab-palette-gtk.css"
            ).read_text()
        ).replace(
            f"palette: {variant}",
            "palette: V",
        )
        for variant in variants
    }

    check(
        "variants are identical except for colours",
        len(shapes) == 1,
    )

    print(
        "\n=== surfaces reference only existing tokens"
    )

    targets = [
        path
        for path in sorted(SURFACES.iterdir())
        if path.is_file()
        and path.suffix
        in (
            ".css",
            ".config",
            ".rasi",
            ".jsonc",
            ".ini",
            ".toml",
        )
    ]

    tokenised = 0

    for path in targets:
        source = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        used = set(
            re.findall(
                r"[@$](hl_\w+)",
                source,
            )
        )

        wired = (
            "/usr/share/hyperlab/palette"
            in source
        )

        if not used and not wired:
            continue

        tokenised += 1

        if wired and not used:
            check(
                f"{path.name}: includes the fragment",
                True,
            )

        unknown = sorted(used - known)

        check(
            f"{path.name}: {len(used)} token",
            not unknown,
            f"unknown: {unknown}",
        )

        declared = allowed_literals()

        found = {
            match.lower()
            for match in re.findall(
                r"#[0-9a-fA-F]{6}",
                source,
            )
        }

        literals = sorted(
            found - set(declared)
        )

        check(
            f"{path.name}: no undeclared colour",
            not literals,
            (
                f"remaining {literals} - "
                "if intentional, add them to "
                "derivate.txt with a reason"
            ),
        )

        used_exceptions = sorted(
            found & set(declared)
        )

        if used_exceptions:
            print(
                "       "
                f"{len(used_exceptions)} "
                "declared derived colours: "
                f"{', '.join(used_exceptions)}"
            )

    check(
        "at least two surfaces are connected to the palette",
        tokenised >= 2,
        f"found {tokenised}",
    )

    print(
        f"\n{'=' * 58}\n"
        f"passed {len(PASSED)}, "
        f"failed {len(FAILED)}"
    )

    print(
        "SURFACES: "
        + (
            "OK"
            if not FAILED
            else f"{len(FAILED)} errors"
        )
    )

    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
