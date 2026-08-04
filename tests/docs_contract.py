#!/usr/bin/env python3
"""User-facing documentation must stay navigable and executable."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
MARKDOWN = [README, *sorted(DOCS.rglob("*.md")), ROOT / "tools/hyperlabctl/README.md"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def local_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [match.group(1).strip() for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text)]


def main() -> int:
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
