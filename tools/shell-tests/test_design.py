#!/usr/bin/env python3
"""Design inconsistencies rather than syntax failures.

A destructive button that looks ordinary, a disabled control without a tooltip,
or a card without a title will not crash Python. These are exactly the defects
that otherwise appear only at the final visual gate.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gtkstub
gtkstub.install()
spec = importlib.util.spec_from_file_location(
    "manager", Path(__file__).resolve().parent.parent.parent / "roles/desktop/files/privatestack-hyperlab-domains.py")
manager = importlib.util.module_from_spec(spec)
sys.modules["manager"] = manager
spec.loader.exec_module(manager)
from test_sections import window  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name, condition, detail=""):
    (PASSED if condition else FAILED).append(name)
    print("  %s %s%s" % ("ok  " if condition else "FAIL", name,
                         "  — " + detail if detail and not condition else ""))


def build_all():
    trees = {}
    for section in manager.SECTIONS:
        win = window("overlay", section)
        trees[section] = getattr(manager.HyperlabWindow, "_build_%s" % section)(win)
    return trees


def main() -> int:
    src = (Path(__file__).resolve().parent.parent.parent / "roles/desktop/files/privatestack-hyperlab-domains.py").read_text(encoding="utf-8")
    trees = build_all()
    widgets = [w for tree in trees.values() for w in tree.walk()]

    print("=== buttons")
    buttons = [w for w in widgets if type(w).__name__ == "Button"]
    check("every button has a label or child",
          all(b.label or b.children for b in buttons),
          "%d unlabeled" % sum(1 for b in buttons if not b.label and not b.children))
    disabled = [b for b in buttons if not b.sensitive]
    check("every disabled button explains why in its tooltip",
          all(b.tooltip for b in disabled),
          "%d without a tooltip: %s" % (sum(1 for b in disabled if not b.tooltip),
                                    [b.label for b in disabled if not b.tooltip]))

    print("\n=== destructive actions")
    # The action registry lives in hyperlabctl rather than the manager. Looking
    # for it here returned zero and falsely looked like a manager defect.
    registry = Path(__file__).resolve().parent.parent / "hyperlabctl/hyperlabctl/registry.py"
    if registry.is_file():
        text = registry.read_text(encoding="utf-8")
        destructive = re.findall(r'"destructive":\s*True', text)
        check("the registry declares destructive actions", len(destructive) >= 3,
              "found %d" % len(destructive))
    else:
        print("  ...  registry.py not available beside the test: check skipped")
    check("the manager requires exact confirmation", "exact_confirm" in src)
    guarded = re.findall(r'exact_confirm\(', src)
    check("exact confirmation is used more than once", len(guarded) >= 2,
          "%d calls" % len(guarded))

    print("\n=== cards and titles")
    # Two card forms are valid: titled cards and metric tiles using
    # metric-value + metric-label. Requiring card-title from both created six
    # false positives.
    cards = [w for w in widgets if w.has_css_class("card")]
    def labelled(c):
        return any(x.has_css_class("card-title") or x.has_css_class("metric-label")
                   or x.has_css_class("page-title") for x in c.walk())
    unlabelled = [c for c in cards if not labelled(c)]
    check("every card has a title or metric",
          not unlabelled,
          "%d without one: %s" % (len(unlabelled),
                            [[x.label for x in c.walk() if x.label][:2] for c in unlabelled]))

    print("\n=== five domains")
    ids = ("clean", "dev", "lab", "dirty", "services")
    check("DOMAIN_META declares five domains", len(manager.DOMAIN_META) == 5)
    check("each domain has a title, subtitle, detail, and class",
          all(all(k in manager.DOMAIN_META[d] for k in
                  ("title", "subtitle", "detail", "css")) for d in ids))
    cubes = Path(__file__).resolve().parent.parent.parent / "roles/desktop/files"
    check("every domain icon points at the deployed cube path",
          all(manager.DOMAIN_META[d]["icon"] ==
              "/usr/share/icons/hyperlab/domains/%s.svg" % d for d in ids))
    missing = [d for d in ids if not (cubes / ("domain-%s.svg" % d)).is_file()]
    check("every domain icon has its source asset", not missing,
          "no source SVG for: %s" % ", ".join(missing))
    check("no typographic glyph is used as a domain icon",
          "◆" not in src and "text_label(\"■\"" not in src,
          "font-dependent glyphs remain")

    print("\n=== text")
    # An empty hidden placeholder is valid because it is populated on demand.
    # Only visible empty labels count.
    empty = [w for w in widgets
             if type(w).__name__ == "Label" and w.label == "" and w.visible]
    check("no visible label is empty", not empty, "%d empty" % len(empty))
    long_labels = [w.label for w in widgets
                   if type(w).__name__ == "Label" and w.label
                   and len(w.label) > 120 and not w.props.get("wrap")]
    check("no long text is missing wrapping", not long_labels,
          "%d above 120 characters without wrapping" % len(long_labels))

    print("\n=== language")
    # Count common English words across longer labels. This catches accidental
    # regressions to a different UI language without relying on accents.
    shown = [w.label for w in widgets if w.label and len(w.label) > 12]
    english_words = ("the ", "and ", "with ", "from ", "for ", "no ",
                     "this ", "image", "system", "available", "control")
    hits = sum(1 for label in shown if any(word in label.lower() for word in english_words))
    check("the interface is in English", shown and hits >= len(shown) * 0.30,
          "%d English labels across %d long strings" % (hits, len(shown)))

    print("\n=== absent fields")
    nones = [w.label for w in widgets if w.label and "None" in w.label]
    check("no absent field is rendered as None", not nones,
          "%d: %s" % (len(nones), nones[:4]))

    print("\n=== surfaces")
    check("the drawer does not build heavy sections",
          "_build_create" not in src[src.index("_build_drawer_shell"):
                                     src.index("_build_drawer_shell") + 3000])
    check("every declared section has a builder",
          all(hasattr(manager.HyperlabWindow, "_build_%s" % s) for s in manager.SECTIONS))

    print("\n%s\npassed %d, failed %d" % ("=" * 58, len(PASSED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
