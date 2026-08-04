#!/usr/bin/env python3
"""The choices source must reject anything that is not a valid decision."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml

import choices as mod

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"  {'ok  ' if condition else 'FAIL'} {name}"
          f"{'  — ' + detail if detail and not condition else ''}")


def main() -> int:
    doc = mod.load()
    print("=== source invariants")
    check("no structural problems", mod.check(doc) == [], str(mod.check(doc)))
    check("every choice has at least two alternatives",
          all(len(entry["options"]) >= 2 for entry in doc["choices"].values()))
    check("every active value is an alternative",
          all(str(entry["value"]) in {str(key) for key in entry["options"]}
              for entry in doc["choices"].values()))
    check("every choice declares affected files",
          all(entry["affects"] for entry in doc["choices"].values()))

    print("\n=== validator mutations")
    broken = {"choices": {"x": {"question": "?", "value": "c", "decided_by": "sid",
                                 "affects": ["f"], "options": {"a": "…", "b": "…"}}}}
    check("rejects a value outside the alternatives", mod.check(broken) != [])
    lonely = {"choices": {"x": {"question": "?", "value": "a", "decided_by": "sid",
                                 "affects": ["f"], "options": {"a": "…"}}}}
    check("rejects a choice with one alternative", mod.check(lonely) != [])
    orphan = {"choices": {"x": {"question": "?", "value": "a", "decided_by": "sid",
                                 "affects": [], "options": {"a": "…", "b": "…"}}}}
    check("rejects a choice with no affected files", mod.check(orphan) != [])

    print("\n=== set")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "choices.yml"
        shutil.copy(mod.SOURCE, copy)
        original, mod.SOURCE = mod.SOURCE, copy
        try:
            try:
                mod.set_value("desktop_palette", "rainbow")
                check("rejects an invented value", False)
            except mod.Refused:
                check("rejects an invented value", True)
            try:
                mod.set_value("missing_theme", "green")
                check("rejects a missing choice", False)
            except mod.Refused:
                check("rejects a missing choice", True)
            mod.set_value("desktop_palette", "violet")
            after = yaml.safe_load(copy.read_text())
            check("writes an accepted value",
                  after["choices"]["desktop_palette"]["value"] == "violet")
            untouched = {name: entry["value"] for name, entry in doc["choices"].items()
                         if name != "desktop_palette"}
            check("does not change other choices",
                  all(after["choices"][name]["value"] == value for name, value in untouched.items()))
            check("keeps the source valid and complete",
                  len(after["choices"]) == len(doc["choices"]))
        finally:
            mod.SOURCE = original

    print("\n=== panel")
    page = mod.panel(doc)
    check("every choice appears in the panel", all(name in page for name in doc["choices"]))
    check("every alternative appears in the panel",
          all(str(key) in page for entry in doc["choices"].values() for key in entry["options"]))
    check("the panel is self-contained",
          "http://" not in page and "https://" not in page and "<script" not in page)

    print("\n=== group variables")
    emitted = yaml.safe_load(mod.group_vars(doc))
    check("the emitted block is valid YAML", isinstance(emitted, dict))
    check("emits a value and alternatives for every choice",
          all(name in emitted and f"{name}_options" in emitted for name in doc["choices"]))
    check("emitted values match active values",
          all(str(emitted[name]) == str(entry["value"]) for name, entry in doc["choices"].items()))

    print(f"\n{'=' * 58}\npassed {len(PASSED)}, failed {len(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
