#!/usr/bin/env python3
"""User-facing documentation must stay navigable and executable.

Every note in problems/ is listed in problems/README.md exactly once: a
note missing from the index is not found from its symptom, and a listed
twice index reads as two problems
(problems/problem-index-missing-and-duplicate-entries.md).

Every checked roadmap entry that claims a hardware observation (it says
Nitro-verified or Predator-verified, opens a "(Nitro" note, says "on
Nitro", or calls itself physical) names its evidence: an `evidence:` link
to an acceptance receipt in docs/, or the words "operator-observed,
unpublished". An entry is the checkbox line with its continuation lines.
ADRs 0017, 0018 and 0022 carry one recognized Status line right below
their title, and their index entries open with the same status. This
proves the structure of a reference, not that an observation is authentic
or that a receipt is enough for the claim.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
MARKDOWN = [README, *sorted(DOCS.rglob("*.md")), ROOT / "tools/hyperlabctl/README.md"]

UNPUBLISHED = "operator-observed, unpublished"
HARDWARE_CLAIM = re.compile(
    r"\b(?:Nitro|Predator)-verified\b"
    r"|\((?:Nitro|Predator)\b"
    r"|\bon (?:the )?(?:Nitro|Predator)\b(?!')"
    r"|\b(?i:physical(?:ly)?)\b"
)
CHECKBOX = re.compile(r"^(?P<indent> *)- \[(?P<mark>.)\] (?P<text>.*)$")
LIST_ITEM = re.compile(r"^ *(?:[-*+]|\d+\.) ")
EVIDENCE_LINK = re.compile(r"\bevidence: \[[^\]]*\]\(([^)]*)\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
STATUS_SCOPED_ADRS = (
    "0017-shell-machine-creation.md",
    "0018-disposable-discards-on-stop.md",
    "0022-network-trust-and-gpu-policy.md",
)
ADR_STATUS = re.compile(r"^Status: (proposed|accepted)\b")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def local_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [match.group(1).strip() for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text)]


def checkbox_entries(text: str) -> list[tuple[int, bool, str]]:
    """(first line, checked, whole text) of every checkbox entry.

    A continuation line is a non-blank line indented deeper than its
    checkbox that does not start another list item; a nested checkbox is an
    entry of its own.
    """
    entries: list[tuple[int, bool, list[str]]] = []
    indent = -1
    for number, line in enumerate(text.splitlines(), start=1):
        match = CHECKBOX.match(line)
        if match:
            require(
                match["mark"] in (" ", "x"),
                f"roadmap line {number}: unknown checkbox mark [{match['mark']}]",
            )
            entries.append((number, match["mark"] == "x", [match["text"].strip()]))
            indent = len(match["indent"])
            continue
        depth = len(line) - len(line.lstrip(" "))
        if indent >= 0 and line.strip() and depth > indent and not LIST_ITEM.match(line):
            entries[-1][2].append(line.strip())
            continue
        indent = -1
    return [(number, checked, " ".join(parts)) for number, checked, parts in entries]


def evidence_refusal(root: Path, base: Path, raw: str) -> str | None:
    """Why a roadmap evidence target is not an acceptance receipt, or None."""
    if not raw or raw != raw.strip() or SCHEME.match(raw) or raw.startswith(("/", "#")):
        return "is not a relative path inside the repository"
    target = unquote(raw.split("#", 1)[0])
    resolved = (base / target).resolve()
    if not resolved.is_relative_to(root):
        return "escapes the repository"
    if not resolved.is_file():
        return "is not an existing file"
    relative = resolved.relative_to(root)
    if (
        len(relative.parts) != 2
        or relative.parts[0] != "docs"
        or relative.suffix != ".md"
        or "acceptance" not in relative.stem
    ):
        return "is not an acceptance receipt in docs/"
    return None


def check_roadmap_evidence(root: Path) -> None:
    roadmap = root / "docs" / "roadmap.md"
    for number, checked, text in checkbox_entries(roadmap.read_text(encoding="utf-8")):
        targets = EVIDENCE_LINK.findall(text)
        for raw in targets:
            refusal = evidence_refusal(root, roadmap.parent, raw)
            require(refusal is None, f"roadmap line {number}: evidence target {raw!r} {refusal}")
        if checked and HARDWARE_CLAIM.search(text):
            require(
                UNPUBLISHED in text or bool(targets),
                f"roadmap line {number}: checked hardware claim names neither an "
                f"evidence: receipt nor {UNPUBLISHED!r}",
            )


def adr_status(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    statuses = [line for line in lines if re.match(r"^(?:- )?Status:", line)]
    require(len(statuses) == 1, f"{path.name} has {len(statuses)} Status lines, not one")
    require(bool(lines) and lines[0].startswith("# ADR "), f"{path.name} lost its title")
    first = next((line for line in lines[1:] if line.strip()), "")
    require(first == statuses[0], f"{path.name}: the Status line is not right below the title")
    match = ADR_STATUS.match(first)
    require(match is not None, f"{path.name}: unrecognized status line {first!r}")
    return match[1]


def adr_index_entries(text: str) -> dict[str, str]:
    """File name -> description of every numbered entry in the ADR index."""
    entries: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        match = re.match(r"^\d+\. \[`([^`]+)`\]\(\1\)(.*)$", line)
        if match:
            require(match[1] not in entries, f"ADR index lists {match[1]} twice")
            current = entries[match[1]] = [match[2].strip()]
        elif current is not None and line.startswith("    ") and line.strip():
            current.append(line.strip())
        else:
            current = None
    return {name: " ".join(parts).lstrip("— ").strip() for name, parts in entries.items()}


def check_adr_status(root: Path) -> None:
    adr = root / "docs" / "adr"
    index = adr_index_entries((adr / "README.md").read_text(encoding="utf-8"))
    for name in STATUS_SCOPED_ADRS:
        status = adr_status(adr / name)
        require(name in index, f"ADR index omits {name}")
        require(
            index[name].startswith(f"{status}: "),
            f"ADR index entry of {name} does not open with its status {status!r}",
        )


def main() -> int:
    check_adr_status(ROOT)
    check_roadmap_evidence(ROOT)

    for path in MARKDOWN:
        text = path.read_text(encoding="utf-8")
        require("Hyperlab" not in text, f"stale product spelling in {path.relative_to(ROOT)}")
        require(
            "ansible-playbook playbooks/" not in text,
            f"manual become command lacks -K in {path.relative_to(ROOT)}",
        )
        for raw_target in local_links(path):
            if raw_target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(raw_target.split("#", 1)[0])
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            require(
                resolved.is_relative_to(ROOT) and resolved.exists(),
                f"broken local link in {path.relative_to(ROOT)}: {raw_target}",
            )

    problems = ROOT / "problems"
    index = (problems / "README.md").read_text(encoding="utf-8")
    for note in sorted(problems.glob("*.md")):
        if note.name == "README.md":
            continue
        listed = len(re.findall(r"\(%s\)" % re.escape(note.name), index))
        require(listed == 1, f"problems/README.md lists {note.name} {listed} times, not once")

    for path in sorted(DOCS.glob("*.md")):
        inbound = any(
            source != path and path.name in source.read_text(encoding="utf-8")
            for source in MARKDOWN
        )
        require(inbound, f"orphaned top-level document: {path.relative_to(ROOT)}")

    for obsolete in (
        "hyperlab-control-center.md",
        "hyperlab-controls.md",
        "hyperlab-native-swaybar-themes.md",
        "hyperlab-wallpaper-modes.md",
    ):
        require(not (DOCS / obsolete).exists(), f"obsolete duplicate document returned: {obsolete}")

    readme = README.read_text(encoding="utf-8")
    require("### Fast path after the first boot" in readme, "README fast path missing")
    require("docs/desktop.md" in readme, "desktop guide is not linked from README")
    require(
        "ansible-playbook -K playbooks/lab.yml   # must end with changed=0" in readme,
        "fast path does not state the idempotence gate",
    )

    choices = (DOCS / "choices.html").read_text(encoding="utf-8")
    require("awaiting Sid" not in choices, "resolved desktop choices still look pending")
    require("7 selected, 2 deferred" in choices, "choice summary is stale")

    roadmap = (DOCS / "roadmap.md").read_text(encoding="utf-8")
    for milestone in ("M10", "M11", "M12", "M13"):
        require(milestone in roadmap, f"roadmap omits {milestone}")

    print("documentation contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
