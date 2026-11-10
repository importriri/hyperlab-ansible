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
unpublished". An entry is the checkbox line with its indented continuation
paragraphs, including those separated by blank lines.
The v1 host target, playbooks/v1-host.yml, is what README's first run and
fast path, the playbook map and the release host-convergence runbook use
for check/diff, first apply and second apply. Their bash blocks are parsed
into command argv; a comment or prose naming a playbook is not a command.
lab.yml and the component playbooks stay documented as narrower targets.
ADRs 0017, 0018 and 0022 carry one recognized Status line right below
their title, and their index entries open with the same status. This
proves the structure of a reference, not that an observation is authentic
or that a receipt is enough for the claim.

The ADR index's proposal inventory has exactly one entry per numbered
record whose own Status line says proposed (in any letter case), and none
for any other record; a record without a Status line is neither proposed
nor accepted. Every entry links its record and fills the Decision, Built,
Activation, Source and Prerequisites fields with a known label, and a
claimed build names existing source files inside the repository. This
checks consistency and paths only: source inspection and review establish
what an entry means, and no entry accepts a decision or records a physical
observation.
"""

from __future__ import annotations

import re
import shlex
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
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

ADR_RECORD = re.compile(r"^(?P<number>\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
STATUS_LINE = re.compile(r"^(?:- )?status:", re.IGNORECASE)
DECLARED_STATUS = re.compile(r"^(?:- )?status:\s*(?P<status>proposed|accepted)\b", re.IGNORECASE)
INVENTORY_HEADING = "## Proposed decisions and their code"
INVENTORY_ENTRY = re.compile(r"^- \[ADR (?P<number>\d{4})\]\((?P<target>[^()\s]+)\)$")
INVENTORY_FIELD = re.compile(r"^  - (?P<field>[A-Za-z]+): (?P<text>.*)$")
INVENTORY_FIELDS = ("Decision", "Built", "Activation", "Source", "Prerequisites")
BUILT_LABELS = ("none", "partial", "built")
ACTIVATION_LABELS = ("none", "default", "on request", "opt-in", "not established")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]*)\)")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def local_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [match.group(1).strip() for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text)]


def checkbox_entries(text: str) -> list[tuple[int, bool, str]]:
    """(first line, checked, whole text) of every checkbox entry.

    A continuation line is a non-blank line indented deeper than its
    checkbox that does not start another list item. Blank lines preserve
    the checkbox context for further paragraphs; a nested checkbox is an
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
        if not line.strip():
            continue
        depth = len(line) - len(line.lstrip(" "))
        if indent >= 0 and depth > indent and not LIST_ITEM.match(line):
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


def check_checkbox_paragraphs() -> None:
    """Paragraph breaks retain an observation without borrowing evidence."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        roadmap = root / "docs" / "roadmap.md"
        roadmap.parent.mkdir()
        for blank in ("", "   "):
            for boundary in ("An unrelated paragraph.", "## A heading", "- Another list item"):
                text = (
                    "- [x] A checked component\n"
                    f"{blank}\n"
                    "      Nitro-verified: operator-observed, unpublished\n"
                    f"{blank}\n"
                    "      The observation keeps its original scope.\n"
                    f"{blank}\n"
                    f"{boundary}\n"
                    f"{blank}\n"
                    "- [x] Another component on Nitro: operator-observed, unpublished\n"
                )
                roadmap.write_text(text, encoding="utf-8")
                check_roadmap_evidence(root)
                roadmap.write_text(text.replace(UNPUBLISHED, "unqualified", 1), encoding="utf-8")
                try:
                    check_roadmap_evidence(root)
                except AssertionError as error:
                    require(
                        str(error).startswith("roadmap line 1: checked hardware claim"),
                        f"second-paragraph observation failed for an unrelated reason: {error}",
                    )
                else:
                    raise AssertionError("unqualified second-paragraph hardware claim was accepted")
                entries = checkbox_entries(text)
                require(
                    entries == [
                        (
                            1,
                            True,
                            "A checked component Nitro-verified: operator-observed, unpublished "
                            "The observation keeps its original scope.",
                        ),
                        (
                            9,
                            True,
                            "Another component on Nitro: operator-observed, unpublished",
                        ),
                    ],
                    f"checkbox paragraphs or entry boundaries changed: {entries!r}",
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


V1_HOST = "playbooks/v1-host.yml"
CONVERGENCE = [
    ["ansible-playbook", "-K", V1_HOST, "--check", "--diff"],
    ["ansible-playbook", "-K", V1_HOST],
    ["ansible-playbook", "-K", V1_HOST],
]
CONTROL_OPERATORS = {"|", "|&", ";", "&&", "||", "&", ">", ">>", "<", "(", ")"}
FENCE = re.compile(r"^(`{3,})(\S*)\s*$")
HEADING = re.compile(r"^(#{1,6}) ")


def markdown_section(path: Path, heading: str) -> list[str]:
    """Lines under one unique heading, up to the next heading of its level.

    Fenced code is skipped while looking for headings, so a shell comment
    inside a block never ends a section.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    heading_match = HEADING.match(heading)
    require(heading_match is not None, f"not a Markdown heading: {heading!r}")
    level = len(heading_match[1])
    starts: list[int] = []
    fence = ""
    for number, line in enumerate(lines):
        match = FENCE.match(line)
        if match and (not fence or match[1] == fence):
            fence = "" if fence else match[1]
            continue
        if not fence and line == heading:
            starts.append(number)
    require(len(starts) == 1, f"{path.name}: heading {heading!r} occurs {len(starts)} times")
    body: list[str] = []
    fence = ""
    for line in lines[starts[0] + 1:]:
        match = FENCE.match(line)
        if match and (not fence or match[1] == fence):
            fence = "" if fence else match[1]
        elif not fence:
            found = HEADING.match(line)
            if found and len(found[1]) <= level:
                break
        body.append(line)
    return body


def bash_blocks(lines: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    fence = ""
    for line in lines:
        match = FENCE.match(line)
        if current is None and match:
            fence = match[1]
            current = [] if match[2] == "bash" else None
            if current is None:
                fence = ""
            continue
        if current is not None and match and match[1] == fence and not match[2]:
            blocks.append("\n".join(current))
            current = None
            continue
        if current is not None:
            current.append(line)
    require(current is None, "unterminated bash block")
    return blocks


def ansible_commands(block: str) -> list[list[str]]:
    """argv of every ansible-playbook command, cut at its first operator."""
    commands: list[list[str]] = []
    for logical in block.replace("\\\n", " ").splitlines():
        lexer = shlex.shlex(logical, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        argv: list[str] = []
        for token in lexer:
            if token in CONTROL_OPERATORS:
                break
            argv.append(token)
        if argv and argv[0] == "ansible-playbook":
            commands.append(argv)
    return commands


def section_commands(path: Path, heading: str) -> list[list[str]]:
    blocks = bash_blocks(markdown_section(path, heading))
    require(bool(blocks), f"{path.name}: {heading!r} has no bash block")
    return ansible_commands(blocks[0])


def check_v1_host_commands(root: Path) -> None:
    """Check/diff, first and second apply all name the v1 host target."""
    readme = root / "README.md"
    playbook_map = root / "docs" / "playbooks.md"
    release = root / "docs" / "release-evidence.md"
    preflight = ["ansible-playbook", "-K", "playbooks/preflight.yml"]
    for path, heading, expected in (
        (readme, "## Start here", [preflight, *CONVERGENCE]),
        (readme, "### Fast path after the first boot", [preflight, *CONVERGENCE]),
        (playbook_map, "### `playbooks/v1-host.yml`", CONVERGENCE),
        (release, "## 5. Host convergence", CONVERGENCE),
    ):
        actual = section_commands(path, heading)
        require(
            actual == expected,
            f"{path.name} {heading!r}: release host commands are {actual!r}, not {expected!r}",
        )
    convergence = "\n".join(markdown_section(release, "## 5. Host convergence"))
    for recap in ("changed=0", "failed=0", "unreachable=0"):
        require(recap in convergence, f"release host convergence no longer requires {recap}")
    # The component and recovery targets stay documented.
    lab = section_commands(playbook_map, "### `playbooks/lab.yml`")
    require(
        lab == [[argv[0], argv[1], "playbooks/lab.yml", *argv[3:]] for argv in CONVERGENCE],
        f"playbooks.md lost the lab.yml component commands: {lab!r}",
    )
    narrow = {
        match[1]
        for line in markdown_section(playbook_map, "## Narrow host reconciliation")
        if (match := re.match(r"^- `([^`]+\.yml)`", line))
    }
    for component in (
        "host-desktop-sway.yml",
        "looking-glass.yml",
        "host-desktop-hyprland.yml",
        "host-sleep-guard.yml",
    ):
        require(component in narrow, f"playbooks.md no longer lists {component}")


def check_v1_host_command_parsing() -> None:
    """Drift in only one apply is seen; prose and comments are not commands."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "docs").mkdir()
        apply = f"ansible-playbook -K {V1_HOST}"
        block = (
            "```bash\n"
            "# ansible-playbook -K playbooks/lab.yml\n"
            f"{apply} --check --diff \\\n  |& tee check.log\n"
            f"{apply} |& tee first.log\n"
            f"{apply}   # must end with changed=0\n"
            "```\n"
        )
        start = "```bash\nansible-playbook -K playbooks/preflight.yml\n" + block[8:]
        lab = block.replace(V1_HOST, "playbooks/lab.yml")
        narrow = "".join(
            f"- `{name}` — component.\n"
            for name in (
                "host-desktop-sway.yml",
                "looking-glass.yml",
                "host-desktop-hyprland.yml",
                "host-sleep-guard.yml",
            )
        )
        release = (
            "## 5. Host convergence\n\nchanged=0, failed=0 and unreachable=0.\n\n" + block
        )
        (root / "README.md").write_text(
            f"## Start here\n\n{start}\n### Fast path after the first boot\n\n{start}",
            encoding="utf-8",
        )
        (root / "docs" / "playbooks.md").write_text(
            f"### `playbooks/v1-host.yml`\n\n{block}\n### `playbooks/lab.yml`\n\n{lab}\n"
            f"## Narrow host reconciliation\n\n{narrow}",
            encoding="utf-8",
        )
        (root / "docs" / "release-evidence.md").write_text(release, encoding="utf-8")
        check_v1_host_commands(root)
        second = release.replace(f"{apply} |& tee first.log\n{apply}", (
            f"{apply} |& tee first.log\nansible-playbook -K playbooks/lab.yml"
        ))
        require(second != release, "fixture did not drift the second apply")
        (root / "docs" / "release-evidence.md").write_text(second, encoding="utf-8")
        try:
            check_v1_host_commands(root)
        except AssertionError as error:
            require("release-evidence.md" in str(error), f"unexpected refusal: {error}")
        else:
            raise AssertionError("a second release apply of lab.yml was accepted")


def declared_status(path: Path) -> str | None:
    """The status a numbered ADR declares, lower case, or None without one.

    A record without a Status line is neither proposed nor accepted. A
    second Status line, one that is not right below the title, or a status
    word other than proposed or accepted is a refusal. An unrecognized
    Status header below the title cannot silently become a legacy record.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    first = next((line for line in lines[1:] if line.strip()), "")
    require(
        "status" not in first.lower() or STATUS_LINE.match(first) is not None,
        f"{path.name}: unrecognized status line {first!r}",
    )
    statuses = [line for line in lines if STATUS_LINE.match(line)]
    if not statuses:
        return None
    require(len(statuses) == 1, f"{path.name} has {len(statuses)} Status lines, not one")
    require(bool(lines) and lines[0].startswith("# ADR "), f"{path.name} lost its title")
    require(first == statuses[0], f"{path.name}: the Status line is not right below the title")
    match = DECLARED_STATUS.match(first)
    require(match is not None, f"{path.name}: unrecognized status line {first!r}")
    return match["status"].lower()


def adr_records(adr: Path) -> dict[str, Path]:
    """File name -> path of every numbered ADR record, numbers unique."""
    records: dict[str, Path] = {}
    numbers: dict[str, str] = {}
    for path in sorted(adr.iterdir()):
        if not (re.match(r"^\d{4}-", path.name) and path.name.endswith(".md")):
            continue
        match = ADR_RECORD.match(path.name)
        require(match is not None, f"{path.name} is not a well-formed ADR file name")
        require(
            path.is_file() and not path.is_symlink(),
            f"{path.name} is not a regular ADR file",
        )
        number = match["number"]
        require(number not in numbers, f"ADR {number} is both {numbers.get(number)} and {path.name}")
        numbers[number] = path.name
        records[path.name] = path
    return records


def inventory_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) of the proposal inventory section of the index."""
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == INVENTORY_HEADING]
    require(
        len(starts) == 1,
        f"ADR index has {len(starts)} {INVENTORY_HEADING!r} sections, not one",
    )
    body: list[tuple[int, str]] = []
    for number, line in enumerate(lines[starts[0] + 1:], start=starts[0] + 2):
        if re.match(r"^#{1,2} ", line):
            break
        body.append((number, line))
    return body


def inventory_entries(text: str) -> dict[str, tuple[int, str, dict[str, str]]]:
    """Linked file -> (line, ADR number, fields) of every inventory entry.

    An entry is a top-level `- [ADR NNNN](file)` item followed directly by
    its `  - Field: text` items, each field continued by lines indented
    four spaces; a blank line ends the entry. Prose may precede the first
    entry. Any other top-level list item in the section, and any other line
    after the first entry, is malformed.
    """
    entries: dict[str, tuple[int, str, dict[str, list[str]]]] = {}
    fields: dict[str, list[str]] | None = None
    field: list[str] | None = None
    started = False
    for number, line in inventory_lines(text):
        malformed = f"ADR index line {number}: malformed proposal inventory line {line!r}"
        heading = INVENTORY_ENTRY.match(line)
        if heading:
            started = True
            name = heading["target"]
            require(name not in entries, f"proposal inventory lists {name} twice")
            fields = {}
            field = None
            entries[name] = (number, heading["number"], fields)
            continue
        require(not line.startswith("- "), malformed)
        if not started:
            continue
        if not line.strip():
            fields = field = None
            continue
        item = INVENTORY_FIELD.match(line)
        if item and fields is not None:
            key = item["field"]
            require(key in INVENTORY_FIELDS, f"ADR index line {number}: unknown inventory field {key!r}")
            require(key not in fields, f"ADR index line {number}: inventory field {key} repeated")
            field = fields[key] = [item["text"].strip()]
            continue
        continued = line.startswith("    ") and not line.lstrip().startswith("- ")
        require(field is not None and continued, malformed)
        assert field is not None
        field.append(line.strip())
    return {
        name: (number, adr, {key: " ".join(parts).strip() for key, parts in values.items()})
        for name, (number, adr, values) in entries.items()
    }


def field_label(text: str, labels: tuple[str, ...], where: str, field: str) -> str:
    """The label a Built or Activation field opens with, before its description."""
    for label in sorted(labels, key=len, reverse=True):
        prefix = f"{label} — "
        if text.startswith(prefix) and text[len(prefix):].strip():
            return label
    raise AssertionError(
        f"{where}: {field} does not open with one of {', '.join(labels)} and a description"
    )


def source_refusal(root: Path, base: Path, raw: str) -> str | None:
    """Why an inventory source link is not an existing source file, or None."""
    if not raw or raw != raw.strip() or SCHEME.match(raw) or raw.startswith(("/", "#")):
        return "is not a relative path inside the repository"
    target = unquote(raw.split("#", 1)[0])
    if not target:
        return "is not a relative path inside the repository"
    resolved = (base / target).resolve()
    if not resolved.is_relative_to(root):
        return "escapes the repository"
    if not resolved.is_file():
        return "is not an existing file"
    relative = resolved.relative_to(root)
    if relative.parts[0] == "docs" or any(part.startswith(".") for part in relative.parts):
        return "is not a source or verification file"
    return None


def check_proposal_inventory(root: Path) -> None:
    root = root.resolve()
    adr = root / "docs" / "adr"
    records = adr_records(adr)
    proposed = {name for name, path in records.items() if declared_status(path) == "proposed"}
    text = (adr / "README.md").read_text(encoding="utf-8")
    navigation = adr_index_entries(text)
    for name in records:
        require(name in navigation, f"ADR index navigation omits {name}")
    entries = inventory_entries(text)
    for name, (line, number, fields) in entries.items():
        where = f"proposal inventory entry {name} (ADR index line {line})"
        record = ADR_RECORD.match(name)
        require(record is not None, f"{where}: the link is not a numbered ADR file name")
        assert record is not None
        require(name in records, f"{where}: the linked record does not exist")
        require(record["number"] == number, f"{where} links ADR {number} to a different record")
        require(name in proposed, f"proposal inventory lists {name}, whose Status is not proposed")
        for key in INVENTORY_FIELDS:
            require(key in fields, f"{where} lacks {key}")
            require(bool(fields[key]), f"{where} has an empty {key}")
        require(
            re.match(r"proposed\b", fields["Decision"], re.IGNORECASE) is not None,
            f"{where}: Decision does not say proposed",
        )
        built = field_label(fields["Built"], BUILT_LABELS, where, "Built")
        active = field_label(fields["Activation"], ACTIVATION_LABELS, where, "Activation")
        require(
            (built == "none") == (active == "none"),
            f"{where}: Built {built!r} and Activation {active!r} disagree",
        )
        links = MARKDOWN_LINK.findall(fields["Source"])
        if fields["Source"] == "none":
            require(built == "none", f"{where}: a {built} build names no source")
        else:
            require(built != "none", f"{where}: nothing is built, so Source must be none")
            require(bool(links), f"{where}: Source is neither none nor source links")
        for raw in links:
            refusal = source_refusal(root, adr, raw)
            require(refusal is None, f"{where}: source link {raw!r} {refusal}")
    for name in sorted(proposed - entries.keys()):
        raise AssertionError(f"proposal inventory omits {name}")


def check_inventory_fixtures() -> None:
    """The inventory check accepts harmless edits and refuses each break."""
    entries = inventory_entries((DOCS / "adr" / "README.md").read_text(encoding="utf-8"))
    sources = sorted(
        {raw for _, _, fields in entries.values() for raw in MARKDOWN_LINK.findall(fields["Source"])}
    )
    with TemporaryDirectory() as directory:
        scratch = Path(directory).resolve()
        (scratch / "outside.py").write_text("", encoding="utf-8")
        root = scratch / "repo"
        adr = root / "docs" / "adr"

        def reset() -> None:
            if root.exists():
                shutil.rmtree(root)
            shutil.copytree(DOCS / "adr", adr)
            for raw in [*sources, "../../.github/workflows/ci.yml"]:
                relative = (DOCS / "adr" / unquote(raw.split("#", 1)[0])).resolve().relative_to(ROOT)
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, root / relative)

        def edit(name: str, old: str, new: str) -> None:
            path = adr / name
            text = path.read_text(encoding="utf-8")
            require(old in text, f"fixture anchor {old!r} is missing from {name}")
            path.write_text(text.replace(old, new, 1), encoding="utf-8")

        def block(name: str) -> str:
            text = (adr / "README.md").read_text(encoding="utf-8")
            match = re.search(
                rf"^- \[ADR {name[:4]}\]\({re.escape(name)}\)\n(?:[^\n]+\n)*",
                text,
                re.MULTILINE,
            )
            require(match is not None, f"fixture entry {name} is missing")
            assert match is not None
            return match[0]

        def without(entry: str, key: str) -> str:
            kept: list[str] = []
            dropping = False
            for line in entry.splitlines(keepends=True):
                if line.startswith("  - "):
                    dropping = line.startswith(f"  - {key}: ")
                if not dropping:
                    kept.append(line)
            require(len(kept) < len(entry.splitlines()), f"fixture field {key} is missing")
            return "".join(kept)

        def accepts(label: str, *edits: tuple[str, str, str]) -> None:
            reset()
            for name, old, new in edits:
                edit(name, old, new)
            try:
                check_proposal_inventory(root)
            except AssertionError as error:
                raise AssertionError(f"inventory control {label} was refused: {error}") from None

        def refuses(label: str, expected: str, *edits: tuple[str, str, str]) -> None:
            reset()
            for name, old, new in edits:
                edit(name, old, new)
            try:
                check_proposal_inventory(root)
            except Exception as error:  # noqa: BLE001 - a crash is not the refusal
                require(
                    isinstance(error, AssertionError) and expected in str(error),
                    f"inventory mutation {label} failed for another reason: "
                    f"{type(error).__name__}: {error}",
                )
            else:
                raise AssertionError(f"inventory mutation {label} was accepted")

        def status_line(name: str) -> str:
            line = next(
                (line for line in (adr / name).read_text(encoding="utf-8").splitlines()
                 if STATUS_LINE.match(line)),
                None,
            )
            require(line is not None, f"fixture record {name} has no Status line")
            assert line is not None
            return line

        def recased(name: str, upper: bool) -> tuple[str, str, str]:
            line = status_line(name)
            match = DECLARED_STATUS.match(line)
            require(match is not None, f"fixture record {name} has no recognized Status")
            assert match is not None
            head = match[0].upper() if upper else match[0].lower()
            return (name, line, head + line[len(match[0]):])

        # Members are chosen from the tree, so accepting or adding a record
        # changes which ones are exercised, never whether the checks run.
        index = "README.md"
        reset()
        statuses = {name: declared_status(path) for name, path in adr_records(adr).items()}
        members = sorted(name for name, status in statuses.items() if status == "proposed")
        accepted = sorted(name for name, status in statuses.items() if status == "accepted")
        built = [name for name in members if entries[name][2]["Source"] != "none"]
        require(len(members) >= 2 and bool(accepted) and bool(built), "too few fixture records")
        target = built[-1]
        other = next(name for name in members if name != target)
        number = target[:4]
        heading = f"- [ADR {number}]({target})"
        target_entry = block(target)
        other_entry = block(other)
        source = MARKDOWN_LINK.search(target_entry.split("  - Source: ", 1)[1])
        require(source is not None, f"fixture entry {target} has no source link")
        assert source is not None

        target_status = status_line(target)
        recase = (recased(target, True), recased(other, False))

        def relinked(new: str) -> tuple[str, str, str]:
            return (index, target_entry, target_entry.replace(f"]({source[1]})", f"]({new})", 1))

        accepts("unchanged")
        accepts(
            "harmless wording",
            (index, f"{INVENTORY_HEADING}\n", f"{INVENTORY_HEADING}\n\nAn added paragraph.\n"),
            (index, "  - Prerequisites: ", "  - Prerequisites: Still open: "),
        )
        accepts("Status letter case", *recase)
        refuses("entry removed", f"proposal inventory omits {target}", (index, target_entry, ""))
        refuses(
            "entry duplicated",
            f"proposal inventory lists {target} twice",
            (index, other_entry, f"{other_entry}\n{target_entry}"),
        )
        refuses(
            "accepted record substituted",
            f"proposal inventory lists {accepted[0]}, whose Status is not proposed",
            (index, heading, f"- [ADR {accepted[0][:4]}]({accepted[0]})"),
        )
        refuses(
            "Status removed from a member",
            f"proposal inventory lists {target}, whose Status is not proposed",
            (target, f"{target_status}\n", ""),
        )
        refuses(
            "Status line duplicated",
            f"{target} has 2 Status lines, not one",
            (target, f"{target_status}\n", f"{target_status}\n\nStatus: accepted.\n"),
        )
        for malformed in ("**Status:** proposed.", "Status : proposed"):
            refuses(
                f"unrecognized Status {malformed!r}",
                f"{target}: unrecognized status line {malformed!r}",
                (target, target_status, malformed),
                (index, target_entry, ""),
            )
        refuses(
            "number mismatched",
            f"links ADR {other[:4]} to a different record",
            (index, heading, f"- [ADR {other[:4]}]({target})"),
        )
        refuses(
            "malformed entry",
            "malformed proposal inventory line",
            (index, heading, f"- [ADR {number[1:]}]({target})"),
        )
        refuses(
            "escaping record link",
            "the link is not a numbered ADR file name",
            (index, heading, f"- [ADR {number}](../adr/{target})"),
        )
        refuses(
            "navigation link removed",
            f"ADR index navigation omits {target}",
            (index, f"[`{target}`]({target})", f"`{target}`"),
        )
        for key in INVENTORY_FIELDS:
            refuses(f"{key} removed", f"lacks {key}", (index, target_entry, without(target_entry, key)))
        refuses(
            "Decision accepted",
            "Decision does not say proposed",
            (index, target_entry, re.sub(
                r"  - Decision: [^\n]+", "  - Decision: accepted; the record remains proposed.",
                target_entry, count=1,
            )),
        )
        refuses(
            "unknown Built label",
            "Built does not open with one of",
            (index, target_entry, target_entry.replace("  - Built: ", "  - Built: complete, ", 1)),
        )
        refuses(
            "build without source",
            "build names no source",
            (index, target_entry, re.sub(r"  - Source: .*\n(?:    .*\n)*", "  - Source: none\n", target_entry)),
        )
        refuses("source missing", "is not an existing file", relinked("../../tools/no-such-source.py"))
        refuses("source escaping", "escapes the repository", relinked("../../../outside.py"))
        refuses(
            "source absolute",
            "is not a relative path inside the repository",
            relinked(str(scratch / "outside.py")),
        )
        refuses("source is documentation", "is not a source or verification file", relinked(other))
        refuses(
            "source is hidden",
            "is not a source or verification file",
            relinked("../../.github/workflows/ci.yml"),
        )


def check_v3_release_runbook(root: Path) -> None:
    """Parse the documented argv and execute the complete synthetic rehearsal."""
    import hashlib
    import json
    import os
    import subprocess
    from release_acceptance_contract import REVIEWED_V3_EVIDENCE

    path = root / "docs/release-evidence.md"
    blocks = bash_blocks(path.read_text().splitlines())
    operations: set[str] = set()
    for block in blocks:
        heredoc = False
        for line in block.replace("\\\n", " ").splitlines():
            if heredoc:
                if line == "PY":
                    heredoc = False
                continue
            argv = shlex.split(line, comments=True)
            if argv[:1] == ["if"]:
                argv = argv[1:]
            if "<<'PY'" in line:
                heredoc = True
            if len(argv) < 2 or argv[1] not in ("tools/release_acceptance.py", "tools/release_probe.py"):
                continue
            require(argv[:4] == ["python", argv[1], "--manifest", "release/acceptance.v3.yml"],
                    f"release runbook command does not select v3: {argv!r}")
            operations.add(argv[4])
    require(operations == {"plan", "scaffold", "repository-proof", "payload", "storage",
                           "idempotence", "record", "status", "seal"},
            f"release runbook omits an executable operation: {operations!r}")
    section = markdown_section(path, "## 3. Run the gates in order")
    text = "\n".join(section)
    order = re.findall(r"^```text\n(.*?)\n```", text, re.MULTILINE | re.DOTALL)
    require(len(order) == 1 and order[0].splitlines() == list(REVIEWED_V3_EVIDENCE),
            "release runbook gate order differs from the reviewed v1 scope")
    rehearsal = bash_blocks(markdown_section(path, "## Synthetic fixture rehearsal"))
    require(len(rehearsal) == 1, "release runbook needs one complete fixture block")
    with TemporaryDirectory() as td:
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", rehearsal[0]],
                                cwd=root, text=True, capture_output=True, check=False,
                                env={**os.environ, "FIXTURE_DIR": td, "PYTHONDONTWRITEBYTECODE": "1"})
        require(result.returncode == 0, f"release runbook fixture failed: {result.stderr}")
        for profile in ("nitro-3060", "predator-3070"):
            fixture = Path(td) / profile
            plan = json.loads((fixture / "plan.json").read_text())
            evidence = json.loads((fixture / "evidence.json").read_text())
            receipt = json.loads((fixture / "receipt.json").read_text())
            require(plan["schema_version"] == evidence["schema_version"] == receipt["schema_version"] == 3,
                    "runbook rehearsal mixed schema versions")
            require(receipt["gate_ids"] == list(REVIEWED_V3_EVIDENCE), "runbook fixture omitted a gate")
            require(receipt["gate_count"] == 19 and receipt["result"] == "pass", "fixture receipt differs")
            for artifact, data in (("plan", plan), ("evidence", evidence)):
                canonical = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
                require(receipt[f"{artifact}_sha256"] == hashlib.sha256(canonical).hexdigest(),
                        f"runbook receipt {artifact} hash differs")
            require(not (fixture / "pending-receipt.json").exists(), "pending fixture wrote a receipt")
            for gate in evidence["gates"]:
                classes = REVIEWED_V3_EVIDENCE[gate["id"]]
                require(set(gate["evidence"]) == {field for fields in classes.values() for field in fields},
                        f"runbook fixture field omission: {gate['id']}")
                for field in classes["booleans"]:
                    require(gate["evidence"][field] is True, f"runbook fixture untyped boolean: {field}")


def main() -> int:
    check_v3_release_runbook(ROOT)
    check_checkbox_paragraphs()
    check_v1_host_command_parsing()
    check_v1_host_commands(ROOT)
    check_adr_status(ROOT)
    check_proposal_inventory(ROOT)
    check_inventory_fixtures()
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
        "ansible-playbook -K playbooks/v1-host.yml   # must end with changed=0" in readme,
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
