#!/usr/bin/env python3
"""Structural wiring contract for the shared HyperLab Quickshell source.

Green structural contracts that only grep for strings cannot tell whether the
shell can actually instantiate. The C9 convergence defect -- a root that
assigned `machineActions` to a bar which declares no such property, while the
component that required it received none -- was invisible to every existing
gate and fatal at startup.

This contract parses the QML component vocabulary and checks two things that
a text search cannot:

  1. every required property of a HyperLab component is assigned wherever
     that component is instantiated;
  2. a property name that belongs to the HyperLab vocabulary is only ever
     assigned to a component that actually declares it.

It deliberately says nothing about Qt's own properties: this is a contract
about HyperLab's own wiring, not a QML type checker.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab"

# Provided by the view that creates a delegate, never by a parent binding.
VIEW_PROVIDED = {"modelData", "index"}

# Assigned by Quickshell's Variants from its model.
VARIANT_PROVIDED = {"modelData"}

PROPERTY_DECLARATION = re.compile(
    r"^[ \t]*(?:(required)[ \t]+)?(?:readonly[ \t]+)?property[ \t]+"
    r"(?:alias[ \t]+|[A-Za-z_][\w.<>]*[ \t]+)([A-Za-z_]\w*)",
    re.MULTILINE,
)

SIGNAL_DECLARATION = re.compile(
    r"^\s*signal\s+([A-Za-z_]\w*)\s*\(",
    re.MULTILINE,
)

ROOT_TYPE = re.compile(
    r"^(?:\s*//[^\n]*\n|\s*\n|\s*import[^\n]*\n|\s*pragma[^\n]*\n)*"
    r"\s*([A-Z][\w.]*)\s*\{",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"HyperLab QML wiring contract: {message}")


def strip_noise(source: str) -> str:
    """Remove comments and string literals so braces can be counted."""
    out: list[str] = []
    index = 0
    length = len(source)

    while index < length:
        char = source[index]

        if char == "/" and source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end < 0 else end
            continue

        if char == "/" and source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue

        if char in "\"'":
            quote = char
            out.append(" ")
            index += 1
            while index < length:
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == quote:
                    index += 1
                    break
                index += 1
            continue

        out.append(char)
        index += 1

    return "".join(out)


def components() -> dict[str, dict[str, object]]:
    """Every HyperLab component, its base type and what it declares."""
    found: dict[str, dict[str, object]] = {}

    for path in sorted(QML.glob("*.qml")):
        name = path.stem

        if name == "shell":
            continue

        source = strip_noise(path.read_text(encoding="utf-8"))
        match = ROOT_TYPE.match(source)
        require(match is not None, f"{path.name}: no resolvable root type")

        declared = {
            item[1] for item in PROPERTY_DECLARATION.findall(source)
        }
        required = {
            item[1] for item in PROPERTY_DECLARATION.findall(source)
            if item[0] == "required"
        }

        found[name] = {
            "base": match.group(1),
            "declared": declared,
            "required": required,
            "signals": set(SIGNAL_DECLARATION.findall(source)),
            "path": path,
        }

    return found


def resolve(name: str, catalogue: dict[str, dict[str, object]], key: str):
    """Collect a declaration set across the HyperLab inheritance chain."""
    collected: set[str] = set()
    seen: set[str] = set()
    current = name

    while current in catalogue and current not in seen:
        seen.add(current)
        collected |= catalogue[current][key]
        current = catalogue[current]["base"]

    return collected


def blocks(source: str, type_name: str, skip_root: bool = True):
    """Yield the body of every assignment block of `type_name`.

    The file's own root element is not an instantiation: whoever instantiates
    the component supplies its required properties, so the root is skipped.
    """
    pattern = re.compile(r"(?<![\w.])" + re.escape(type_name) + r"\s*\{")
    root = ROOT_TYPE.match(source)
    root_start = root.end() if (skip_root and root) else -1

    for match in pattern.finditer(source):
        start = match.end()

        if start == root_start:
            continue

        depth = 1
        index = start

        while index < len(source) and depth:
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
            index += 1

        yield source[start:index - 1]


def assignments(body: str) -> set[str]:
    """Property names bound at the top level of one object body."""
    names: set[str] = set()
    depth = 0
    index = 0
    line_start = True

    token = re.compile(r"\s*([A-Za-z_]\w*)\s*:")

    while index < len(body):
        char = body[index]

        if char in "{[(":
            depth += 1
            line_start = True
            index += 1
            continue

        if char in "}])":
            depth -= 1
            line_start = True
            index += 1
            continue

        if char in ";\n,":
            line_start = True
            index += 1
            continue

        if char.isspace():
            index += 1
            continue

        if depth == 0 and line_start:
            match = token.match(body, index)
            if match:
                names.add(match.group(1))
                index = match.end()
                line_start = False
                continue

        line_start = False
        index += 1

    return names


def main() -> int:
    catalogue = components()
    require(bool(catalogue), "no HyperLab QML components found")

    # The wiring vocabulary is the set of properties HyperLab components
    # actually require. Optional properties and Qt's own property names are
    # deliberately out of scope: this contract is about injection, not types.
    vocabulary: set[str] = set()
    for entry in catalogue.values():
        vocabulary |= entry["required"]

    problems: list[str] = []

    for path in sorted(QML.glob("*.qml")):
        source = strip_noise(path.read_text(encoding="utf-8"))

        for type_name in catalogue:
            if type_name == path.stem:
                continue

            declared = resolve(type_name, catalogue, "declared")
            required = resolve(type_name, catalogue, "required")
            signals = resolve(type_name, catalogue, "signals")

            handlers = {"on" + name[0].upper() + name[1:] for name in signals}

            for body in blocks(source, type_name):
                bound = assignments(body)

                # A delegate declares the properties its view provides.
                inline = {
                    item[1] for item in PROPERTY_DECLARATION.findall(body)
                }

                missing = required - bound - inline - VIEW_PROVIDED
                if missing:
                    problems.append(
                        "%s instantiates %s without required %s"
                        % (path.name, type_name, sorted(missing))
                    )

                stray = (
                    (bound & vocabulary)
                    - declared
                    - handlers
                    - inline
                    - VARIANT_PROVIDED
                )
                if stray:
                    problems.append(
                        "%s assigns %s to %s, which declares no such property"
                        % (path.name, sorted(stray), type_name)
                    )

    # The root is the one file that must wire everything the surfaces need.
    shell = strip_noise((QML / "shell.qml").read_text(encoding="utf-8"))

    for surface in (
        "HyperLabBar",
        "HyperLabDesktop",
        "WorkspaceSurface",
        "SystemPanel",
        "OsdSurface",
        "LauncherSurface",
        "ShellIpc",
    ):
        require(
            surface in catalogue,
            f"root surface component missing: {surface}",
        )
        require(
            len(list(blocks(shell, surface, False))) == 1,
            f"root does not instantiate exactly one {surface}",
        )

    if problems:
        for problem in problems:
            print("  " + problem)

    require(not problems, f"{len(problems)} wiring defects")

    print(
        "HyperLab Quickshell QML wiring contract: OK (%d components)"
        % len(catalogue)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
