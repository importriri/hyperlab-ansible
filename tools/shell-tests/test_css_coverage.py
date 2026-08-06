#!/usr/bin/env python3
"""Every CSS class added by the code must exist in the stylesheet, and vice versa.

A class passed to add_css_class but absent from CSS changes nothing and never
fails: it is invisible in every sense. This is how `.drawer-status` once shipped
without a rule.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

DOMAINS = ("clean", "dev", "lab", "dirty", "services")


def classes_used(src: str) -> set[str]:
    """Return only classes that can be resolved statically.

    A regex over `add_css_class(...)` also captures `meta["css"]` and invents a
    phantom `.css` class. The AST distinguishes constants from dictionary keys,
    so no exception list is needed.
    """
    tree = ast.parse(src)
    found: set[str] = set()

    def constants(node: ast.AST):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.IfExp):
            yield from constants(node.body)
            yield from constants(node.orelse)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            # "domain-badge-%s" % x  -> expand across the five domains
            for template in constants(node.left):
                if "%s" in template:
                    for domain in DOMAINS:
                        yield template % domain

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else \
            node.func.id if isinstance(node.func, ast.Name) else ""
        if name == "add_css_class":
            args = node.args
        elif name in ("set_css", "text_label", "card_title"):
            args = node.args[1:]
        elif name == "button":
            args = node.args[2:]
        else:
            continue
        for arg in args:
            found |= set(constants(arg))

    # values declared as classes in metadata tables
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if (isinstance(key, ast.Constant) and key.value == "css"
                        and isinstance(value, ast.Constant)):
                    found.add(value.value)

    return {c for c in found if re.fullmatch(r"[a-z][\w-]*", c)}


def classes_defined(css: str) -> set[str]:
    body = re.sub(r"\{[^}]*\}", "{}", css)
    return set(re.findall(r"\.([a-z][\w-]*)", body))


def main(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    css = re.search(r'CSS = r"""(.*?)"""', src, re.S).group(1)
    used, defined = classes_used(src), classes_defined(css)

    missing = sorted(used - defined)
    unused = sorted(defined - used)
    print(f"classes used by code: {len(used)}   defined in CSS: {len(defined)}")
    print(f"\n### used without a CSS rule ({len(missing)})")
    for name in missing:
        print(f"   FAIL .{name}")
    print(f"\n### defined but never applied ({len(unused)})")
    for name in unused:
        print(f"   warn .{name}")
    print("\n" + "=" * 58)
    if missing:
        print(f"CSS COVERAGE: {len(missing)} classes without a rule")
        return 1
    print(f"CSS COVERAGE: OK  ({len(unused)} unused rules)")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent.parent / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
    raise SystemExit(main(target))
