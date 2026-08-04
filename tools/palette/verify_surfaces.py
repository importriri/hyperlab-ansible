#!/usr/bin/env python3
"""Every token referenced by a surface must exist in the generated fragments.

An undefined `@hl_something` changes no colour and may fail silently in GTK or Sway, just like a CSS class without a rule.

The reverse is checked too: hand-written hexadecimal colours in tokenised surfaces are a second source and must be declared.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render_palette import TOKENS  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
SURFACES = REPO / "roles/desktop/files"
def allowed_literals() -> dict[str, str]:
    """Exceptions live in a file rather than a constant so every addition is visible in the diff and undeclared colours keep failing verification.
    """
    path = Path(__file__).parent / "derivate.txt"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#  ") or line.startswith("# "):
            continue
        if line.startswith("#") and len(line) >= 7:
            parts = line.split(None, 1)
            if len(parts[0]) == 7:
                out[parts[0].lower()] = parts[1] if len(parts) > 1 else ""
    return out

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"  {'ok  ' if condition else 'FAIL'} {name}"
          f"{'  — ' + detail if detail and not condition else ''}")


def main(argv: list[str]) -> int:
    fragments = Path(argv[1]) if len(argv) > 1 else SURFACES / "palette"
    known = {f"hl_{token}" for token in TOKENS}

    print("=== fragments define every token")
    variants = sorted(p.name for p in fragments.iterdir() if p.is_dir())
    check("at least two variants", len(variants) >= 2, f"found {variants}")
    for variant in variants:
        gtk = fragments / variant / "hyperlab-palette-gtk.css"
        defined = set(re.findall(r"@define-color\s+(hl_\w+)", gtk.read_text(encoding="utf-8")))
        check(f"{variant}: {len(TOKENS)} tokens defined", defined == known,
              f"missing {sorted(known - defined)}")
    shapes = {re.sub(r"#[0-9a-fA-F]{6}", "X",
                     (fragments / v / "hyperlab-palette-gtk.css").read_text())
              .replace(f"palette: {v}", "palette: V") for v in variants}
    check("variants are identical except for colours", len(shapes) == 1)

    print("\n=== surfaces reference only existing tokens")
    targets = [p for p in sorted(SURFACES.iterdir())
               if p.is_file() and p.suffix in (".css", ".config", ".rasi", ".jsonc", ".ini", ".toml")]
    tokenised = 0
    for path in targets:
        text = path.read_text(encoding="utf-8", errors="ignore")
        used = set(re.findall(r"[@$](hl_\w+)", text))
        wired = "/usr/share/hyperlab/palette" in text
        if not used and not wired:
            continue
        tokenised += 1
        if wired and not used:
            # Sway consumes tokens from the fragment's client.* lines; the include is the required wiring.
            check(f"{path.name}: includes the fragment", True)
        unknown = sorted(used - known)
        check(f"{path.name}: {len(used)} token", not unknown, f"unknown: {unknown}")
        declared = allowed_literals()
        found = {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}", text)}
        literals = sorted(found - set(declared))
        check(f"{path.name}: no undeclared colour", not literals,
              f"remaining {literals} - if intentional, add them to derivate.txt with a reason")
        used_exceptions = sorted(found & set(declared))
        if used_exceptions:
            print(f"       {len(used_exceptions)} declared derived colours: "
                  f"{', '.join(used_exceptions)}")
    check("at least two surfaces are connected to the palette", tokenised >= 2,
          f"found {tokenised}")

    print(f"\n{'=' * 58}\npassed {len(PASSED)}, failed {len(FAILED)}")
    print("SURFACES: " + ("OK" if not FAILED else f"{len(FAILED)} errors"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
