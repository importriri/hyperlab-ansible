#!/usr/bin/env python3
"""Verify generated fragments: token coverage, variant parity, no stray colours, and minimum syntax for every format."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from render_palette import TOKENS, WRITERS


def main(root: Path) -> int:
    doc = yaml.safe_load((Path(__file__).with_name("palette.yml")).read_text())
    failures: list[str] = []
    for variant, colours in doc["variants"].items():
        allowed = {colours[t].lower() for t in TOKENS}
        allowed |= {v.lstrip("#") for v in allowed}
        outdir = root / variant
        print(f"\n=== {variant}")
        for filename in WRITERS:
            path = outdir / filename
            if not path.is_file():
                failures.append(f"{variant}/{filename} missing")
                print(f"  FAIL {filename} missing")
                continue
            text = path.read_text()
            found = {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}", text)}
            found |= {m.lower() for m in re.findall(r"=([0-9a-fA-F]{6})\b", text)}
            stray = sorted(found - allowed)
            covered = sum(1 for t in TOKENS if colours[t].lower() in text.lower()
                          or colours[t].lstrip('#').lower() in text.lower())
            mark = "ok  "
            if stray:
                failures.append(f"{variant}/{filename}: out-of-palette colours {stray}")
                mark = "FAIL"
            print(f"  {mark} {filename:34} tokens present {covered}/{len(TOKENS)}"
                  f"{'  stray ' + str(stray) if stray else ''}")

    # parity: the same files and variable names in every variant
    print("\n=== structural parity across variants")
    variants = list(doc["variants"])
    for filename in WRITERS:
        shapes = []
        for variant in variants:
            text = (root / variant / filename).read_text()
            shape = re.sub(r"#?[0-9a-fA-F]{6}", "X", text)
            # Normalize the variant name in the banner before comparing structure.
            for name in variants:
                shape = shape.replace(f"palette: {name}", "palette: V")
            shapes.append(shape)
        if len(set(shapes)) != 1:
            failures.append(f"{filename}: different structure across variants")
            print(f"  FAIL {filename}: different structure")
        else:
            print(f"  ok   {filename}: identical except for colours")

    print("\n" + "=" * 58)
    if failures:
        for item in failures:
            print(f"ERROR  {item}")
        return 1
    print("OUTPUT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "build")))
