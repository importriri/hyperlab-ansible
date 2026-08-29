#!/usr/bin/env python3
"""Audit the palette before it becomes CSS.

Three invariants, all verifiable without a display:

  1. variant parity       - identical token names, no gaps
  2. WCAG contrast       - text remains readable on every background
  3. domain separation   - the five cubes remain distinguishable and none collides with the accent
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

STRUCTURAL = ("base", "mantle", "surface", "overlay", "text", "subtext")
DOMAINS = ("dom_clean", "dom_dev", "dom_lab", "dom_dirty", "dom_services")
META = ("label", "note")

AA_NORMAL = 4.5
AA_LARGE = 3.0
HUE_MIN = 25.0          # minimum degrees between two domains
ACCENT_HUE_MIN = 20.0   # minimum degrees between a domain and the accent


def rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def luminance(value: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(value)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hue(value: str) -> float:
    r, g, b = (c / 255 for c in rgb(value))
    high, low = max(r, g, b), min(r, g, b)
    if high == low:
        return 0.0
    d = high - low
    if high == r:
        h = ((g - b) / d) % 6
    elif high == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def hue_gap(a: str, b: str) -> float:
    d = abs(hue(a) - hue(b)) % 360
    return min(d, 360 - d)


def audit(path: Path) -> int:
    doc = yaml.safe_load(path.read_text())
    variants = doc["variants"]
    domains = doc.get("domains", {})
    failures: list[str] = []
    warnings: list[str] = []

    names = {k: {n for n in v if n not in META} for k, v in variants.items()}
    reference = next(iter(names.values()))
    print(f"=== 1. variant parity  ({len(variants)} variants, {len(reference)} tokens)")
    for variant, keys in names.items():
        missing, extra = sorted(reference - keys), sorted(keys - reference)
        if missing or extra:
            failures.append(f"{variant}: missing {missing}, extra {extra}")
            print(f"  FAIL {variant}: missing {missing} extra {extra}")
        else:
            print(f"  ok   {variant}")

    default = doc.get("default")
    if default not in variants:
        failures.append(f"default '{default}' is not a variant")
        print(f"  FAIL default '{default}' does not exist")

    required_domains = set(DOMAINS)
    if set(domains) != required_domains:
        failures.append(
            "canonical domains: missing %s, extra %s"
            % (sorted(required_domains - set(domains)), sorted(set(domains) - required_domains))
        )
        print("  FAIL canonical domain token set")
    for variant, tokens in variants.items():
        leaked = sorted(set(tokens) & required_domains)
        if leaked:
            failures.append(f"{variant}: overrides canonical domain tokens {leaked}")
            print(f"  FAIL {variant}: domain overrides {leaked}")

    print("\n=== 2. WCAG contrast (text on every background)")
    for variant, tokens in variants.items():
        print(f"  [{variant}]")
        for fg, floor in (("text", AA_NORMAL), ("subtext", AA_LARGE)):
            for bg in ("base", "mantle", "surface"):
                ratio = contrast(tokens[fg], tokens[bg])
                mark = "ok  " if ratio >= floor else "FAIL"
                if ratio < floor:
                    failures.append(f"{variant}: {fg} on {bg} = {ratio:.2f} (minimum {floor})")
                print(f"    {mark} {fg:8} on {bg:8} {ratio:5.2f}  (minimum {floor})")
        for token in ("accent", "accent2", "ok", "warn", "bad"):
            ratio = contrast(tokens[token], tokens["mantle"])
            mark = "ok  " if ratio >= AA_LARGE else "warn"
            if ratio < AA_LARGE:
                warnings.append(f"{variant}: {token} on mantle = {ratio:.2f}")
            print(f"    {mark} {token:8} on mantle   {ratio:5.2f}  (minimum {AA_LARGE})")

    print("\n=== 3. canonical five-domain separation")
    if required_domains.issubset(domains):
        worst = None
        for i, a in enumerate(DOMAINS):
            for b in DOMAINS[i + 1:]:
                gap = hue_gap(domains[a], domains[b])
                if worst is None or gap < worst[0]:
                    worst = (gap, a, b)
                if gap < HUE_MIN:
                    failures.append(
                        f"canonical domains: {a} and {b} are separated by {gap:.0f} degrees"
                    )
                    print(f"  FAIL {a} vs {b}: {gap:.0f} degrees")
        if worst is not None:
            print(
                f"  closest pair: {worst[1]} / {worst[2]} at "
                f"{worst[0]:.0f} degrees"
            )
        for variant, tokens in variants.items():
            print(f"  [{variant} accent]")
            for domain in DOMAINS:
                gap = hue_gap(domains[domain], tokens["accent"])
                if gap < ACCENT_HUE_MIN:
                    warnings.append(
                        f"{variant}: {domain} is {gap:.0f} degrees from the accent; "
                        "it needs a shape marker as well as colour"
                    )
                    print(f"    warn {domain} vs accent: {gap:.0f} degrees")

    print("\n" + "=" * 62)
    for item in warnings:
        print(f"WARNING  {item}")
    if failures:
        for item in failures:
            print(f"ERROR  {item}")
        print(f"PALETTE: {len(failures)} errors, {len(warnings)} warnings")
        return 1
    print(f"PALETTE: OK  ({len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(audit(Path(sys.argv[1] if len(sys.argv) > 1 else "palette.yml")))
