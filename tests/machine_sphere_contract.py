#!/usr/bin/env python3
"""Execute MachineSphere.qml under Qt's software rasteriser (ADR 0064).

The component is loaded with the real Theme.qml and Tokens.qml and the
rendered trust-model palette. Every state of the ADR's table is drawn for
every domain at 12, 16, 32, 64, 128 and 256 pixels; the checks read the
captured pixels and the runtime accessibility properties, not the source
text. `--contact-sheet PATH` also writes the review sheet (16 to 128 px).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from host_quickshell_qml_wiring_contract import strip_noise
from trust_pool_v3_generated_contract import png_pixels

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab"
COMPONENT = QML / "MachineSphere.qml"
ADR = ROOT / "docs/adr/0064-spheres-are-machines.md"
PALETTE = ROOT / "themes/trust-model/rendered/hyperlab-palette-quickshell.json"
VARIANTS = ROOT / "roles/host_desktop_sway/files/palette"
DOMAINS = ("host", "clean", "dev", "services", "dirty", "lab")
SIZES = (12, 16, 32, 64, 128, 256)
SHEET_SIZES = (16, 32, 64, 128)

# Column label -> component inputs. "unknown" is a state outside the
# vocabulary: it must fail closed to the same neutral outline as external.
CASES: tuple[tuple[str, dict], ...] = (
    ("running", {"state": "running"}),
    ("shut off", {"state": "shut off"}),
    ("starting", {"state": "starting"}),
    ("stopping", {"state": "stopping"}),
    ("paused", {"state": "paused"}),
    ("suspended", {"state": "suspended"}),
    ("external", {"state": "external"}),
    ("unclassified", {"state": "unclassified"}),
    ("disposable", {"state": "running", "disposable": True}),
    ("GPU", {"state": "running", "gpuOwner": True}),
    ("off + GPU", {"state": "shut off", "gpuOwner": True}),
    ("all marks", {"state": "paused", "disposable": True, "gpuOwner": True}),
    ("unknown", {"state": "crashed"}),
)
COLUMN = {label: index for index, (label, _) in enumerate(CASES)}
# States drawn as the neutral outline; "crashed" stands for any word outside
# the vocabulary.
NEUTRAL = ("external", "unclassified", "crashed")
# Each row of the ADR's state table and the columns that draw it.
ADR_ROWS = {
    "running": ("running",),
    "shut off": ("shut off",),
    "starting, stopping": ("starting", "stopping"),
    "paused or suspended": ("paused", "suspended"),
    "disposable": ("disposable",),
    "owns the GPU": ("GPU", "off + GPU"),
    "external, unclassified": ("external", "unclassified"),
}
# Every string literal the component may contain. A colour name ("white",
# "transparent") or any other new literal is a refusal, not a default.
LITERALS = {
    "running", "shut off", "starting", "stopping", "paused", "suspended",
    "shutoff", "in shutdown", "pmsuspended", "host",
    "", "external", "unclassified", "unknown", "Machine", "2d",
    ", ", ", disposable", ", owns the GPU",
}

# The libvirt words the component accepts and the table word each one draws.
ALIASES = {"shutoff": "shut off", "in shutdown": "stopping", "pmsuspended": "suspended"}
# States drawn as a dark but filled body, and the least mean luminance that
# body keeps above the ground, so it never reads as the empty outline.
DARK = ("shut off", "starting", "stopping")
DARK_BODY_LIFT = 8.0
# Least per-channel distance between the neutral outline and the HOST grey or
# any domain colour, under every appearance.
NEUTRAL_DISTANCE = 48
# Least whiteness the specular highlight adds over its own surroundings.
HIGHLIGHT_LIFT = 72

SCENE = r'''
import QtQuick
import QtQuick.Window
import Quickshell

Window {
    id: window
    visible: true
    width: @@WIDTH@@
    height: @@HEIGHT@@
    color: shellTheme.base
    property var samples: []
    property int frame: 0
    // grabToImage reads the content item, not the window colour.
    Rectangle { anchors.fill: parent; color: shellTheme.base }
    Theme { id: shellTheme }
    Tokens { id: metrics; reducedMotion: @@REDUCED@@ }
    Component { id: sphere; MachineSphere {} }
    Component {
        id: label
        Text { color: shellTheme.textPrimary; font.pixelSize: 12 }
    }
    Component.onCompleted: {
        QsHarness.files = {};
        shellTheme.applyPalette(@@PALETTE@@);
        for (const row of @@ROWS@@) {
            const item = sphere.createObject(window.contentItem, {
                theme: shellTheme, tokens: metrics, machineName: "dev-01",
                domain: row.domain, state: row.state,
                disposable: row.disposable || false, gpuOwner: row.gpuOwner || false,
                isHost: row.isHost || false,
                size: row.size, x: row.x, y: row.y
            });
            if (!item) throw new Error("sphere did not instantiate");
            window.samples.push(item);
        }
        for (const row of @@LABELS@@)
            label.createObject(window.contentItem, row);
        capture.start();
    }
    Timer {
        id: capture
        interval: 180
        onTriggered: {
            window.contentItem.grabToImage(function(result) {
                if (!result.saveToFile(@@OUTPUT@@ + window.frame + ".png"))
                    throw new Error("capture failed");
                window.frame += 1;
                if (window.frame < 2) {
                    capture.start();
                    return;
                }
                console.log("SPHERES " + JSON.stringify(window.samples.map(item => ({
                    name: item.Accessible.name, role: item.Accessible.role,
                    ignored: item.Accessible.ignored, graphic: Accessible.Graphic,
                    word: item.domainWord, width: item.width, height: item.height
                }))));
                Qt.quit();
            });
        }
    }
}
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("Machine sphere contract: " + message)


def string_literals(source: str) -> list[str]:
    """Every quoted literal outside comments, in source order."""
    found: list[str] = []
    index = 0
    while index < len(source):
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = len(source) if end < 0 else end
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            require(end >= 0, "unterminated comment")
            index = end + 2
        elif source[index] in "\"'`":
            quote, start = source[index], index + 1
            index = start
            while index < len(source) and source[index] != quote:
                index += 2 if source[index] == "\\" else 1
            require(index < len(source), "unterminated string literal")
            found.append(source[start:index])
            index += 1
        else:
            index += 1
    return found


def source_contract() -> None:
    require(COMPONENT.is_file(), "MachineSphere.qml is missing")
    source = COMPONENT.read_text(encoding="utf-8")
    require(not re.search(r"#[0-9a-fA-F]{3,8}\b", source), "colour literal in component")
    stray = sorted(set(string_literals(source)) - LITERALS)
    require(not stray, f"literal outside the reviewed vocabulary (colour name?): {stray}")
    code = strip_noise(source)
    require(not re.search(r"\bQt\.(?:rgba?|hsla?|hsva?|color|tint)\s*\(", code),
            "colour constructor bypasses the palette")
    require(not re.search(r"\b(?:Process|FileView|MouseArea|TapHandler|Timer|States?)\s*\{", code),
            "a sphere presents confirmed input; it observes, acts and changes state on nothing")
    require(not re.search(r"\bimport\s+Quickshell", code), "sphere must not import host services")


def adr_table() -> list[str]:
    """The State column of the ADR's state table, parsed as a table."""
    require(ADR.is_file(), f"{ADR.relative_to(ROOT)} is missing")
    lines = ADR.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells == ["State", "Drawing"]:
            require(index + 1 < len(lines) and set(lines[index + 1].replace("|", "").strip()) <= {"-", " ", ":"},
                    "state table has no separator row")
            states = []
            for row in lines[index + 2:]:
                if not row.lstrip().startswith("|"):
                    break
                parts = [cell.strip() for cell in row.strip().strip("|").split("|")]
                require(len(parts) == 2 and all(parts), f"malformed state row: {row}")
                states.append(parts[0])
            require(len(states) == len(set(states)), "duplicated state row")
            return states
    raise SystemExit("Machine sphere contract: the ADR has no State | Drawing table")


def prepare(directory: Path) -> None:
    for name in ("MachineSphere.qml", "Theme.qml", "Tokens.qml"):
        shutil.copyfile(QML / name, directory / name)
    # Scope is Quickshell's nonvisual root; keep every Theme binding and give
    # its FileView an inert owner. The stub FileView reads nothing.
    theme = (directory / "Theme.qml").read_text(encoding="utf-8")
    require(theme.count("\nScope {") == 1 and theme.count("\n    FileView {") == 1,
            "Theme.qml no longer has the expected Scope/FileView shape")
    theme = theme.replace("\nScope {", "\nQtObject {", 1)
    theme = theme.replace("\n    FileView {", "\n    property var sourceFile: FileView {", 1)
    (directory / "Theme.qml").write_text(theme, encoding="utf-8")


def render(directory: Path, rows: list[dict], palette: dict, *, reduced: bool = True,
           labels: list[dict] | None = None, geometry: tuple[int, int] | None = None,
           name: str = "capture") -> tuple[list[dict], list[bytes], int]:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    require(bool(runner), "Qt 6 qmlscene is required")
    width, height = geometry or (
        max(row["x"] + row["size"] + 4 for row in rows),
        max(row["y"] + row["size"] + 4 for row in rows),
    )
    substitutions = {
        "WIDTH": str(width), "HEIGHT": str(height),
        "REDUCED": str(reduced).lower(), "PALETTE": json.dumps(json.dumps(palette)),
        "ROWS": json.dumps(rows), "LABELS": json.dumps(labels or []),
        "OUTPUT": json.dumps(str(directory / name)),
    }
    scene = SCENE
    for key, value in substitutions.items():
        scene = scene.replace("@@" + key + "@@", value)
    path = directory / "check.qml"
    path.write_text(scene, encoding="utf-8")
    for frame in (0, 1):
        (directory / f"{name}{frame}.png").unlink(missing_ok=True)
    result = subprocess.run(
        [runner, str(path)], capture_output=True, text=True, check=False, timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "QT_FORCE_STDERR_LOGGING": "1", "QML_DISABLE_DISK_CACHE": "1",
             "QML2_IMPORT_PATH": str(ROOT / "tests/quickshell_stubs"),
             "XDG_CACHE_HOME": str(directory / "cache")},
    )
    lines = (result.stdout + result.stderr).splitlines()
    records = [line.split("SPHERES ", 1)[1] for line in lines if "SPHERES " in line]
    noise = [line for line in lines if line.strip() and "SPHERES " not in line
             and "Semantic palette loaded:" not in line
             and not line.startswith(("qt.tools.qmlscene.deprecated:", "QStandardPaths:"))]
    require(result.returncode == 0 and len(records) == 1 and not noise,
            f"Qt execution failed ({result.returncode}): {noise[:4]}")
    images = [png_pixels(directory / f"{name}{frame}.png", (width, height)) for frame in (0, 1)]
    return json.loads(records[0]), images, width


def grid(size: int, domains: tuple[str, ...] = DOMAINS) -> list[dict]:
    rows = []
    for line, domain in enumerate(domains):
        for column, (_, inputs) in enumerate(CASES):
            rows.append(dict(domain=domain, size=size, x=column * (size + 8) + 4,
                             y=line * (size + 8) + 4, isHost=domain == "host", **inputs))
    return rows


def crop(image: bytes, width: int, row: dict) -> bytes:
    size = row["size"]
    return b"".join(image[((row["y"] + y) * width + row["x"]) * 3:
                          ((row["y"] + y) * width + row["x"] + size) * 3]
                    for y in range(size))


def pixel(picture: bytes, size: int, x: float, y: float) -> tuple[int, int, int]:
    offset = (int(y) * size + int(x)) * 3
    red, green, blue = picture[offset:offset + 3]
    return red, green, blue


def luminance(colour: tuple[int, int, int]) -> float:
    red, green, blue = colour
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def inner_luminance(picture: bytes, size: int) -> list[float]:
    """Luminance of every pixel wholly inside 0.7 of the body radius."""
    centre, reach = size / 2, size * 0.37 * 0.7
    return [luminance(pixel(picture, size, x, y)) for y in range(size) for x in range(size)
            if math.hypot(x + 0.5 - centre, y + 0.5 - centre) + math.sqrt(0.5) <= reach]


def orbit_runs(picture: bytes, size: int, ground: bytes) -> int:
    """Runs of drawn pixels met walking once round the orbit circle."""
    centre, orbit = size / 2, size * 0.43
    drawn = [pixel(picture, size, centre + orbit * math.cos(step * math.pi / 360),
                   centre + orbit * math.sin(step * math.pi / 360)) != tuple(ground)
             for step in range(720)]
    return sum(1 for index, here in enumerate(drawn) if here and not drawn[index - 1])


def rgb(colour: str) -> tuple[int, int, int]:
    require(re.fullmatch(r"#[0-9a-fA-F]{6}", colour) is not None, f"palette colour {colour!r}")
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def near(first: tuple[int, ...], second: tuple[int, ...], tolerance: int = 3) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(first, second, strict=True))


def exterior(size: int) -> list[int]:
    """Offsets of the pixels lying wholly outside the circle of radius size/2.

    A pixel the circle crosses may carry anti-aliasing coverage; one that
    lies entirely beyond it must show the untouched ground.
    """
    centre = size / 2
    offsets = []
    for y in range(size):
        for x in range(size):
            nearest_x = min(max(centre, x), x + 1)
            nearest_y = min(max(centre, y), y + 1)
            if math.hypot(nearest_x - centre, nearest_y - centre) > centre:
                offsets.append((y * size + x) * 3)
    return offsets


def cuts(picture: bytes, size: int, ground: bytes) -> int:
    """Runs of bare ground across the body, at 0.6 of its radius above the centre.

    Only pixels lying wholly inside the body disc are read, so the rim's
    anti-aliasing never counts as a cut.
    """
    centre, body = size / 2, size * 0.37
    y = int(centre - body * 0.6)
    reach = math.sqrt(body * body - max(abs(y - centre), abs(y + 1 - centre)) ** 2)
    runs, previous = 0, False
    for x in range(math.ceil(centre - reach), math.floor(centre + reach)):
        bare = pixel(picture, size, x, y) == tuple(ground)
        runs += bare and not previous
        previous = bare
    return runs


def expected_name(row: dict) -> str:
    state = ALIASES.get(row["state"], row["state"])
    reserved = row.get("isHost", False) == (row["domain"] == "host")
    word = ("external" if state == "external"
            else "unclassified" if state == "unclassified" or not reserved
            or row["domain"] not in DOMAINS else row["domain"])
    return (f"dev-01, {word}, {state}" + (", disposable" if row.get("disposable") else "")
            + (", owns the GPU" if row.get("gpuOwner") else ""))


def check_grid(rows: list[dict], records: list[dict], frames: list[bytes], width: int,
               palette: dict, *, reduced: bool) -> list[bytes]:
    size = rows[0]["size"]
    ground = bytes(rgb(palette["base"]))
    outside = exterior(size)
    first, second = ([crop(frame, width, row) for row in rows] for frame in frames)
    require(len(records) == len(rows), "missing runtime records")
    for row, record, picture, later in zip(rows, records, first, second, strict=True):
        where = f"{row['domain']}/{row['state']}/{size}"
        require((record["width"], record["height"]) == (size, size), f"size: {where}")
        require(record["name"] == expected_name(row) and not record["ignored"]
                and record["role"] == record["graphic"], f"accessible name or role: {where}: {record}")
        require(all(picture[offset:offset + 3] == ground for offset in outside),
                f"drawing escaped the sphere's envelope: {where}")
        moving = not reduced and row["state"] in ("starting", "stopping")
        require((picture != later) == moving,
                f"motion only while a transition is reported, never with reduced motion: {where}")
        if row["state"] in NEUTRAL:
            require(set(inner_luminance(picture, size)) == {luminance(tuple(ground))},
                    f"neutral outline must have no fill: {where}")
        elif row["state"] in DARK:
            inner = inner_luminance(picture, size)
            require(sum(inner) / len(inner) - luminance(tuple(ground)) >= DARK_BODY_LIFT,
                    f"a dark sphere keeps a body above the ground: {where}")

    centre = (size / 2, size / 2)
    for line, domain in enumerate(DOMAINS):
        pictures = dict(zip((label for label, _ in CASES), first[line * len(CASES):], strict=False))
        running, off = pictures["running"], pictures["shut off"]
        require(sum(pixel(running, size, *centre)) > 2 * sum(pixel(off, size, *centre)),
                f"shut off must be a dark sphere: {domain}/{size}")
        require(len({pictures[label] for label in
                     ("running", "shut off", "starting", "stopping", "paused", "external")}) == 6,
                f"two states share one drawing: {domain}/{size}")
        require(pictures["paused"] == pictures["suspended"], f"paused and suspended differ: {domain}/{size}")
        # The pause is two cuts in the silhouette, independent of colour.
        require(cuts(pictures["paused"], size, ground) == 2 and cuts(running, size, ground) == 0,
                f"missing pause notch: {domain}/{size}")
        require(pictures["external"] == pictures["unclassified"] == pictures["unknown"],
                f"external, unclassified and unknown must share the neutral outline: {domain}/{size}")
        require(len({running, pictures["disposable"], pictures["GPU"]}) == 3
                and pictures["off + GPU"] != off and pictures["all marks"] != pictures["paused"],
                f"missing disposable ring or GPU token: {domain}/{size}")
        if size == 64:
            check_marks(domain, size, pictures, ground)
    for label in ("running", "shut off", "paused"):
        drawings = {first[line * len(CASES) + COLUMN[label]] for line in range(len(DOMAINS))}
        require(len(drawings) == len(DOMAINS), f"two domains share one {label} sphere at {size}")
    neutral = {first[line * len(CASES) + COLUMN["external"]] for line in range(len(DOMAINS))}
    require(len(neutral) == 1, f"external depends on the domain input at {size}")
    return first


def check_marks(domain: str, size: int, pictures: dict[str, bytes], ground: bytes) -> None:
    """Where the marks sit and what they look like, read at 64 px."""
    where = f"{domain}/{size}"
    running = pictures["running"]
    require(orbit_runs(running, size, ground) == 0, f"running draws on the orbit: {where}")
    require(orbit_runs(pictures["disposable"], size, ground) >= 8,
            f"the disposable ring is not dashed: {where}")
    # The GPU token is docked on the orbit at the right: every pixel it
    # changes, pins included, lies within its own width of the orbit's right
    # edge, and it covers the orbit there.
    centre, orbit, side = size / 2, size * 0.43, size * 0.16
    changed = [(x, y) for y in range(size) for x in range(size)
               if pixel(pictures["GPU"], size, x, y) != pixel(running, size, x, y)]
    require(bool(changed) and min(x for x, _ in changed) >= centre + orbit - 1.25 * side - 2
            and any(abs(x + 0.5 - (centre + orbit)) <= 2 and abs(y + 0.5 - centre) <= 2
                    for x, y in changed),
            f"the GPU token is not docked on the ring at the right: {where}")
    # The specular highlight whitens its spot well beyond its surroundings.
    body = size * 0.37
    spot = (centre - body * 0.36, centre - body * 0.40)
    around = [pixel(running, size, spot[0] + body * 0.375 * math.cos(step * math.pi / 4),
                    spot[1] + body * 0.375 * math.sin(step * math.pi / 4)) for step in range(8)]
    require(min(pixel(running, size, *spot)) - max(min(colour) for colour in around) >= HIGHLIGHT_LIFT,
            f"missing specular highlight: {where}")


def neutral_rim(picture: bytes, size: int, palette: dict, where: str) -> None:
    """The outline is the appearance text tone and far from every identity colour."""
    colour = pixel(picture, size, size / 2, size / 2 - size * 0.37)
    require(near(colour, rgb(palette["text"])),
            f"neutral outline is not the appearance text tone: {where}: {colour}")
    identities = [rgb(palette["dom_" + domain]) for domain in DOMAINS]
    require(all(max(abs(a - b) for a, b in zip(colour, tint, strict=True)) >= NEUTRAL_DISTANCE
                for tint in identities),
            f"external drawn with the HOST grey or a domain colour: {where}: {colour}")


def check_rims(rows: list[dict], pictures: list[bytes], palette: dict) -> None:
    """At 128 px the rim is wider than a pixel: read its exact colour."""
    size = rows[0]["size"]
    top = (size / 2, size / 2 - size * 0.37)
    for row, picture in zip(rows, pictures, strict=True):
        where = f"{row['domain']}/{row['state']}/{size}"
        colour = pixel(picture, size, *top)
        if row["state"] in ("running", "shut off", "starting", "stopping"):
            require(near(colour, rgb(palette["dom_" + row["domain"]])),
                    f"rim is not the palette domain colour: {where}: {colour}")
        elif row["state"] in NEUTRAL:
            neutral_rim(picture, size, palette, where)


def contact_sheet(directory: Path, palette: dict, destination: Path) -> None:
    rows, labels, column = [], [], 148
    y = 34
    for size in SHEET_SIZES:
        for domain in DOMAINS:
            labels.append({"text": f"{domain} · {size} px", "x": 8, "y": y + size // 2 - 4})
            for index, (_, inputs) in enumerate(CASES):
                rows.append(dict(domain=domain, size=size, x=132 + index * column + (column - size) // 2,
                                 y=y, isHost=domain == "host", **inputs))
            y += max(36, size + 12)
        y += 12
    for index, (label, _) in enumerate(CASES):
        labels.append({"text": label, "x": 132 + index * column + 8, "y": 10})
    render(directory, rows, palette, labels=labels,
           geometry=(132 + len(CASES) * column + 8, y + 8), name="sheet")
    shutil.copyfile(directory / "sheet0.png", destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact-sheet", type=Path)
    args = parser.parse_args()

    source_contract()
    table = adr_table()
    require(sorted(table) == sorted(ADR_ROWS),
            f"ADR states and drawn cases differ: {sorted(set(table) ^ set(ADR_ROWS))}")
    palette = json.loads(PALETTE.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="machine-sphere-") as temporary:
        directory = Path(temporary)
        prepare(directory)
        baseline: list[bytes] = []
        for size in SIZES:
            rows = grid(size)
            records, frames, width = render(directory, rows, palette)
            pictures = check_grid(rows, records, frames, width, palette, reduced=True)
            if size == 128:
                check_rims(rows, pictures, palette)
            if size == 32:
                baseline = pictures

        # Motion: the arc moves only for a reported transition.
        rows = grid(32)
        records, frames, width = render(directory, rows, palette, reduced=False)
        check_grid(rows, records, frames, width, palette, reduced=False)

        # Themes never touch a sphere: identical drawings on every appearance.
        # The neutral outline is the appearance text tone, and under every
        # appearance it stays far from the HOST grey and every domain colour.
        variants = sorted(path.name for path in VARIANTS.iterdir() if path.is_dir())
        require(bool(variants), "no appearance variants to compare")
        outline = [{"domain": domain, "state": state, "size": 128, "x": 4 + index * 136, "y": 4}
                   for index, (domain, state) in enumerate(
                       (domain, state) for domain in DOMAINS for state in NEUTRAL)]
        for variant in variants:
            appearance = json.loads((VARIANTS / variant / "hyperlab-palette-quickshell.json")
                                    .read_text(encoding="utf-8"))
            appearance["base"] = palette["base"]
            _, frames, width = render(directory, rows, appearance)
            for index, row in enumerate(rows):
                if row["state"] not in NEUTRAL:
                    require(crop(frames[0], width, row) == baseline[index],
                            f"theme {variant} changed the {row['domain']}/{row['state']} sphere")
            _, frames, width = render(directory, outline, appearance)
            for row in outline:
                neutral_rim(crop(frames[0], width, row), 128, appearance,
                            f"{variant}/{row['domain']}/{row['state']}")

        # The libvirt words draw the table state they name.
        aliases = [{"domain": domain, "state": word, "size": 32, "x": 4 + index * 40,
                    "y": 4 + line * 40, "isHost": domain == "host"}
                   for line, domain in enumerate(DOMAINS) for index, word in enumerate(ALIASES)]
        records, frames, width = render(directory, aliases, palette)
        for row, record in zip(aliases, records, strict=True):
            line = DOMAINS.index(row["domain"])
            drawn = baseline[line * len(CASES) + COLUMN[ALIASES[row["state"]]]]
            require(crop(frames[0], width, row) == drawn and record["name"] == expected_name(row),
                    f"libvirt state {row['state']!r} does not draw {ALIASES[row['state']]!r}: "
                    f"{row['domain']}: {record['name']}")

        # The neutral outline owes nothing to the domain table, and every
        # domain drawing follows it.
        shifted = dict(palette)
        for index, domain in enumerate(DOMAINS):
            shifted["dom_" + domain] = palette["dom_" + DOMAINS[(index + 1) % len(DOMAINS)]]
        _, frames, width = render(directory, rows, shifted)
        for index, row in enumerate(rows):
            line, column = divmod(index, len(CASES))
            picture = crop(frames[0], width, row)
            if row["state"] in NEUTRAL:
                require(picture == baseline[index], f"external follows a domain colour: {row['domain']}")
            else:
                moved = ((line + 1) % len(DOMAINS)) * len(CASES) + column
                require(picture == baseline[moved],
                        f"sphere does not take its colour from the palette: {row['domain']}/{row['state']}")

        # Fail closed: an incomplete table or an invented domain is neutral.
        neutral = baseline[COLUMN["external"]]
        incomplete = {key: value for key, value in palette.items() if key != "dom_dev"}
        # The HOST grey is the host's own: "host" without the caller's
        # isHost, or isHost with any other domain, is the neutral outline.
        cases = ((incomplete, "dev", False), (incomplete, "host", True), (palette, "invented", False),
                 (palette, "host", False), (palette, "dev", True), (palette, "invented", True))
        for table_input, domain, host in cases:
            single = [{"domain": domain, "state": "running", "size": 32, "x": 4, "y": 4, "isHost": host}]
            records, frames, width = render(directory, single, table_input)
            require(crop(frames[0], width, single[0]) == neutral,
                    f"unresolved identity became a filled sphere: {domain} (isHost {host})")
            if table_input is palette:
                require(records[0]["word"] == "unclassified",
                        f"unresolved identity keeps a domain word: {domain} (isHost {host})")

        if args.contact_sheet:
            contact_sheet(directory, palette, args.contact_sheet)
    print("Machine sphere contract: OK (ADR states, palette-only colour, neutral external, "
          "motion, theme independence, accessibility, 12-256 px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
