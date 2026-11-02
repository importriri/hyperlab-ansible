#!/usr/bin/env python3
"""Contract for the declarative HyperLab theme registry."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml
from jinja2 import Environment, nodes


ROOT = Path(__file__).resolve().parents[1]

THEME = ROOT / "themes/trust-model/theme.yml"
TOOL = ROOT / "tools/theme_registry.py"

CHOICES = "tools/choices/choices.yml"
GENERATED = "group_vars/all/choices.yml"
PALETTE = "tools/palette/palette.yml"
MANIFEST = "themes/trust-model/theme.yml"
INSTALLER = "roles/host_desktop_sway/tasks/palette.yml"
APPEARANCE = {
    "base", "mantle", "surface", "overlay", "text", "subtext",
    "accent", "accent2", "ok", "warn", "bad",
}
PRESETS = {"green", "violet", "blue", "red", "trust-model"}
PALETTES = {
    name: (
        "themes/trust-model/rendered/hyperlab-palette-quickshell.json"
        if name == "trust-model" else
        f"roles/host_desktop_sway/files/palette/{name}/hyperlab-palette-quickshell.json"
    )
    for name in PRESETS
}
INPUTS = (CHOICES, GENERATED, PALETTE, MANIFEST, *sorted(PALETTES.values()))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab theme registry contract: {message}"
        )


def yaml_doc(repo: Path, relative: str) -> dict[str, Any]:
    return yaml.safe_load((repo / relative).read_text(encoding="utf-8"))


def change_yaml(repo: Path, relative: str, edit: Callable[[dict[str, Any]], None]) -> None:
    doc = yaml_doc(repo, relative)
    edit(doc)
    (repo / relative).write_text(yaml.safe_dump(doc), encoding="utf-8")


def change_palette(repo: Path, name: str, edit: Callable[[dict[str, Any]], None]) -> None:
    path = repo / PALETTES[name]
    doc = json.loads(path.read_text(encoding="utf-8"))
    edit(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


def fixture(sandbox: Path) -> Path:
    repo = sandbox / "repo"
    for relative in (*INPUTS, INSTALLER):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for name in ("home", "config", "cache", "data", "state", "runtime"):
        (sandbox / name).mkdir()
    return repo


def snapshot(root: Path) -> dict[str, tuple[int, bytes | str | None]]:
    entries = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if path.is_symlink():
            content = os.readlink(path)
        elif path.is_file():
            try:
                content = path.read_bytes()
            except PermissionError:
                content = "unreadable"
        else:
            content = None
        entries[str(path.relative_to(root))] = (mode, content)
    return entries


def preview(repo: Path, sandbox: Path, *, audit_root: bool = False) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HOME=str(sandbox / "home"))
    for key, name in (
        ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ):
        environment[key] = str(sandbox / name)
    before = snapshot(sandbox)
    command = [sys.executable, "-B", str(TOOL), "--repo", str(repo), "palette-summaries", "--json"]
    if audit_root:
        # Run the same CLI entry point, counting actual root-path opens rather
        # than assuming that resolving a Path pins its directory identity.
        wrapper = """
import runpy
import sys

sys.argv = sys.argv[1:]
root = sys.argv[2]
root_opens = 0

def audit(event, args):
    global root_opens
    if event == "open" and args[0] == root:
        root_opens += 1

sys.addaudithook(audit)
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit:
    if root_opens != 1:
        raise AssertionError("preview must open resolved repository root exactly once")
    raise
"""
        command = [sys.executable, "-B", "-c", wrapper, str(TOOL), "--repo", str(repo.resolve()),
                   "palette-summaries", "--json"]
    result = subprocess.run(
        command,
        check=False, text=True, capture_output=True, env=environment, timeout=15,
    )
    require(snapshot(sandbox) == before, "palette preview wrote to the input tree or HOME/XDG")
    return result


def expected_preview(repo: Path) -> dict[str, Any]:
    # Expectations come from independent input documents, never exporter code.
    variants = yaml_doc(repo, PALETTE)["variants"]
    manifest = yaml_doc(repo, MANIFEST)
    rows = []
    for name in sorted(PRESETS):
        colours = json.loads((repo / PALETTES[name]).read_text(encoding="utf-8"))
        declarative = name == "trust-model"
        rows.append({
            "id": name,
            "label": manifest["name"] if declarative else variants[name]["label"],
            "source_kind": "declarative" if declarative else "legacy",
            "manifest_status": manifest["status"] if declarative else None,
            "manifest_visible": manifest["selector"]["visible"] if declarative else None,
            "appearance": {key: colours[key] for key in APPEARANCE},
        })
    return {"version": 1, "scope": "source-runtime-presets", "presets": rows}


def successful_preview(repo: Path, sandbox: Path) -> str:
    result = preview(repo, sandbox)
    require(result.returncode == 0 and result.stderr == "", f"preview failed: {result.stderr}")
    payload = json.loads(result.stdout)
    require(type(payload["version"]) is int, "preview version must be an integer")
    require(payload == expected_preview(repo), "preview differs from exact per-preset sources/metadata")
    require(
        len({tuple(sorted(row["appearance"].items())) for row in payload["presets"]}) == 5,
        "preview reused appearance across presets",
    )
    for row in payload["presets"]:
        require(all(isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)
                    for v in row["appearance"].values()), "invalid exported appearance")
    trust = next(row for row in payload["presets"] if row["id"] == "trust-model")
    require(trust["manifest_status"] == "scaffold" and trust["manifest_visible"] is False,
            "preview promoted the hidden scaffold")
    return result.stdout


def refused_preview(edit: Callable[[Path], None], diagnostic: str, name: str) -> None:
    with tempfile.TemporaryDirectory(prefix="hyperlab-palette-refusal-") as temporary:
        sandbox = Path(temporary)
        repo = fixture(sandbox)
        edit(repo)
        result = preview(repo, sandbox)
        require(result.stdout == "", f"{name}: refusal leaked successful stdout")
        require(result.returncode == 1, f"{name}: expected deliberate refusal, got {result.returncode}")
        require(result.stderr.startswith("HyperLab theme registry: ")
                and "Traceback" not in result.stderr and diagnostic in result.stderr,
                f"{name}: wrong refusal diagnostic: {result.stderr}")


def check_legacy_installer(repo: Path) -> None:
    tasks = yaml.safe_load((repo / INSTALLER).read_text(encoding="utf-8"))
    installers = [task for task in tasks if task.get("name") == "Install every runtime palette fragment"]
    require(len(installers) == 1, "legacy palette installer must be unique")
    loop = Environment().parse(installers[0]["loop"])
    products = [node for node in loop.find_all(nodes.Filter) if node.name == "product"]
    require(len(products) == 1 and isinstance(products[0].node, nodes.List),
            "legacy palette installer must use an explicit product list")
    items = products[0].node.items
    require(all(isinstance(item, nodes.Const) and isinstance(item.value, str) for item in items),
            "legacy palette installer ids must be string literals")
    installed = [item.value for item in items]
    options = yaml_doc(repo, CHOICES)["choices"]["desktop_palette"]["options"]
    variants = yaml_doc(repo, PALETTE)["variants"]
    legacy = set(options) & set(variants)
    require(len(installed) == len(set(installed)) and legacy == set(installed),
            "legacy runtime presets differ from the installer loop")


def check_palette_summaries() -> None:
    # Test this before success parsing so a streaming exporter fails specifically
    # for partial stdout when its last row is invalid.
    refused_preview(lambda repo: change_palette(repo, "violet", lambda doc: doc.update(accent="invalid")),
                    "colour", "invalid last row")
    with tempfile.TemporaryDirectory(prefix="hyperlab-palette-success-") as temporary:
        sandbox = Path(temporary)
        repo = fixture(sandbox)
        accepted = successful_preview(ROOT, sandbox)
        require(successful_preview(ROOT, sandbox) == accepted, "accepted preview bytes are unstable")
        baseline = successful_preview(repo, sandbox)
        require(baseline == accepted, "fixture and accepted source previews differ")
        require(successful_preview(repo, sandbox) == baseline, "fixture preview bytes are unstable")
        audited = preview(repo, sandbox, audit_root=True)
        require(audited.returncode == 0 and audited.stderr == "" and audited.stdout == baseline,
                f"root descriptor audit failed: {audited.stderr}")
        change_palette(repo, "blue", lambda doc: doc.update(accent="#a1B2c3"))
        changed = successful_preview(repo, sandbox)
        before_rows = json.loads(baseline)["presets"]
        after_rows = json.loads(changed)["presets"]
        require([a["id"] for a, b in zip(after_rows, before_rows, strict=True) if a != b] == ["blue"],
                "a valid appearance edit affected another row")
        change_yaml(repo, PALETTE, lambda doc: doc["variants"]["green"].update(label="Fixture green"))
        change_yaml(repo, MANIFEST, lambda doc: doc.update(name="Fixture Trust Model"))
        successful_preview(repo, sandbox)
        change_yaml(repo, MANIFEST, lambda doc: doc.update(status="retired"))
        change_yaml(repo, MANIFEST, lambda doc: doc["selector"].update(visible=True))
        result = preview(repo, sandbox)
        require(result.returncode == 0 and result.stderr == ""
                and json.loads(result.stdout) == expected_preview(repo),
                "preview ignored edited manifest metadata")
        change_yaml(repo, MANIFEST, lambda doc: doc.update(status="scaffold"))
        change_yaml(repo, MANIFEST, lambda doc: doc["selector"].update(visible=False))
        change_yaml(repo, GENERATED, lambda doc: doc["desktop_palette_options"].reverse())
        successful_preview(repo, sandbox)
        manifest = yaml_doc(repo, MANIFEST)
        manifest.update(id="unlisted", name="Unlisted", status="ready")
        manifest["selector"]["visible"] = True
        extra = repo / "themes/unlisted"
        extra.mkdir()
        (extra / "theme.yml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
        (extra / "rendered").mkdir()
        extra_colours = json.loads((repo / PALETTES["trust-model"]).read_text(encoding="utf-8"))
        extra_colours["name"] = "unlisted"
        (extra / "rendered/hyperlab-palette-quickshell.json").write_text(
            json.dumps(extra_colours), encoding="utf-8")
        successful_preview(repo, sandbox)
        # Even an unreadable unlisted manifest cannot become an input by scanning.
        (extra / "theme.yml").write_text("invalid: [", encoding="utf-8")
        successful_preview(repo, sandbox)
        alias = sandbox / "root-alias"
        alias.symlink_to(repo, target_is_directory=True)
        successful_preview(alias, sandbox)
        expected = expected_preview(repo)
        expected["presets"] = [row for row in expected["presets"] if row["id"] != "blue"]
        change_yaml(repo, CHOICES, lambda doc: doc["choices"]["desktop_palette"]["options"].pop("blue"))
        change_yaml(repo, GENERATED, lambda doc: doc["desktop_palette_options"].remove("blue"))
        (repo / PALETTES["blue"]).unlink()
        result = preview(repo, sandbox)
        require(result.returncode == 0 and result.stderr == "" and json.loads(result.stdout) == expected,
                "preview did not derive its rows/reads from the runtime option set")

    for relative in INPUTS:
        refused_preview(lambda repo, r=relative: (repo / r).unlink(), "", f"missing {relative}")
        refused_preview(lambda repo, r=relative: (repo / r).chmod(0), "", f"unreadable {relative}")
        refused_preview(lambda repo, r=relative: (repo / r).write_bytes(b"\xff"),
                        "", f"invalid encoding {relative}")
        refused_preview(lambda repo, r=relative: (repo / r).write_text("[", encoding="utf-8"),
                        "", f"malformed {relative}")
        refused_preview(lambda repo, r=relative: (repo / r).write_text("[]", encoding="utf-8"),
                        "mapping", f"non-mapping {relative}")

        def redirect(repo: Path, relative: str = relative) -> None:
            path = repo / relative
            external = repo.parent / "external-input"
            shutil.copyfile(path, external)
            path.unlink()
            path.symlink_to(external)

        refused_preview(redirect, "", f"external symlink {relative}")

    for relative in (PALETTE, CHOICES, GENERATED, MANIFEST):
        def invalid_date(repo: Path, relative: str = relative) -> None:
            with (repo / relative).open("a", encoding="utf-8") as stream:
                stream.write("bad_date: 2026-13-45\n")
        refused_preview(invalid_date, "", f"invalid YAML date {relative}")
        refused_preview(lambda repo, r=relative: (repo / r).write_text("[" * 100000, encoding="utf-8"),
                        "", f"excessive YAML nesting {relative}")

    for name in sorted(PRESETS):
        refused_preview(lambda repo, n=name: (repo / PALETTES[n]).write_text(
            '{"oversized": ' + "9" * 5000 + '}', encoding="utf-8"),
            "", f"oversized JSON integer {name}")
        refused_preview(lambda repo, n=name: (repo / PALETTES[n]).write_text(
            "[" * 100000, encoding="utf-8"), "", f"excessive JSON nesting {name}")

    for relative, addition in (
        (CHOICES, "version: 1\n"), (GENERATED, "desktop_palette: green\n"),
        (PALETTE, "default: green\n"), (MANIFEST, "id: trust-model\n"),
    ):
        def duplicate(repo: Path, relative: str = relative, addition: str = addition) -> None:
            with (repo / relative).open("a", encoding="utf-8") as stream:
                stream.write(addition)
        refused_preview(duplicate, "duplicate", f"duplicate YAML {relative}")

    def duplicate_source_id(repo: Path) -> None:
        path = repo / CHOICES
        content = path.read_text(encoding="utf-8")
        content = content.replace("    options:\n", "    options:\n      green: duplicate\n", 1)
        path.write_text(content, encoding="utf-8")
    refused_preview(duplicate_source_id, "duplicate", "duplicate source id")

    def alias_yaml(repo: Path) -> None:
        with (repo / PALETTE).open("a", encoding="utf-8") as stream:
            stream.write("recursive: &self [*self]\n")
    refused_preview(alias_yaml, "aliases", "recursive YAML alias")

    def complex_key(repo: Path) -> None:
        with (repo / PALETTE).open("a", encoding="utf-8") as stream:
            stream.write("? [bad, key]\n: invalid\n")
    refused_preview(complex_key, "mapping key", "complex YAML key")

    for name in sorted(PRESETS):
        for key, value, diagnostic in (
            ("name", "green" if name != "green" else "blue", "palette name"),
            ("accent", "#12345", "colour"), ("text", "red", "colour"),
            ("warn", 123456, "colour"), ("ok", None, "colour"),
            ("bad", True, "colour"), ("base", ["#123456"], "colour"),
            ("surface", "#123456\n", "colour"), ("overlay", "#gggggg", "colour"),
        ):
            refused_preview(lambda repo, n=name, k=key, v=value:
                            change_palette(repo, n, lambda doc: doc.update({k: v})),
                            diagnostic, f"invalid {name} {key}")
        for key in ("accent", "dom_host"):
            refused_preview(lambda repo, n=name, k=key:
                            change_palette(repo, n, lambda doc: doc.pop(k)),
                            "key set", f"missing {name} {key}")
        refused_preview(lambda repo, n=name:
                        change_palette(repo, n, lambda doc: doc.update(command="ignored")),
                        "key set", f"extra key {name}")
        for domain in yaml_doc(ROOT, PALETTE)["domains"]:
            refused_preview(lambda repo, n=name, d=domain:
                            change_palette(repo, n, lambda doc: doc.update({d: "#123456"})),
                            "domain", f"changed {name} {domain}")

        def duplicate_json(repo: Path, name: str = name) -> None:
            path = repo / PALETTES[name]
            content = path.read_text(encoding="utf-8")
            path.write_text(content[:-2] + ', "accent": "#123456"}\n', encoding="utf-8")
        refused_preview(duplicate_json, "duplicate", f"duplicate JSON {name}")

    for bad_id in ("../escape", "/tmp/escape", "Green", "", 12, None):
        refused_preview(lambda repo, value=bad_id: change_yaml(
            repo, CHOICES, lambda doc: doc["choices"]["desktop_palette"].update(options={value: "bad"})),
            "id", f"invalid source id {bad_id!r}")
        refused_preview(lambda repo, value=bad_id: change_yaml(
            repo, GENERATED, lambda doc: doc.update(desktop_palette_options=[value])),
            "id", f"invalid generated id {bad_id!r}")

        def agreeing_invalid_ids(repo: Path, value: Any = bad_id) -> None:
            change_yaml(repo, CHOICES, lambda doc:
                        doc["choices"]["desktop_palette"].update(options={value: "bad"}))
            change_yaml(repo, GENERATED, lambda doc: doc.update(desktop_palette_options=[value]))
        refused_preview(agreeing_invalid_ids, "id", f"agreeing invalid ids {bad_id!r}")
    refused_preview(lambda repo: change_yaml(repo, GENERATED, lambda doc:
                    doc["desktop_palette_options"].append("green")), "duplicate", "duplicate generated id")
    refused_preview(lambda repo: change_yaml(repo, GENERATED, lambda doc:
                    doc["desktop_palette_options"].remove("red")), "disagree", "option disagreement")

    def unknown_option(repo: Path) -> None:
        change_yaml(repo, CHOICES, lambda doc:
                    doc["choices"]["desktop_palette"]["options"].update(unlisted="Unlisted"))
        change_yaml(repo, GENERATED, lambda doc: doc["desktop_palette_options"].append("unlisted"))
    refused_preview(unknown_option, "", "unlisted runtime option has no fallback")
    refused_preview(lambda repo: change_yaml(repo, CHOICES, lambda doc:
                    doc["choices"]["desktop_palette"]["options"].clear()), "options", "empty options")
    refused_preview(lambda repo: change_yaml(repo, CHOICES, lambda doc:
                    doc["choices"]["desktop_palette"].update(options=["green"])), "mapping", "options list")
    refused_preview(lambda repo: change_yaml(repo, GENERATED, lambda doc:
                    doc.update(desktop_palette_options="green")), "list", "options string")
    refused_preview(lambda repo: change_yaml(repo, CHOICES, lambda doc:
                    doc.pop("choices")), "choices", "missing choices")
    refused_preview(lambda repo: change_yaml(repo, PALETTE, lambda doc:
                    doc["variants"]["green"].update(label=12)), "label", "non-string legacy label")
    refused_preview(lambda repo: change_yaml(repo, PALETTE, lambda doc:
                    doc["variants"]["green"].update(label=" ")), "label", "blank legacy label")
    refused_preview(lambda repo: change_yaml(repo, PALETTE, lambda doc:
                    doc["domains"].pop("dom_host")), "key set", "missing canonical domain")
    refused_preview(lambda repo: change_yaml(repo, PALETTE, lambda doc:
                    doc["domains"].update(dom_host=12)), "colour", "invalid canonical domain")
    for edit in (
        lambda doc: doc.update(id="../escape"), lambda doc: doc.update(id="other"),
        lambda doc: doc.update(status="unknown"), lambda doc: doc.update(status=[]),
        lambda doc: doc["selector"].update(visible="false"),
        lambda doc: doc.update(security={"exec": "bad"}),
    ):
        refused_preview(lambda repo, edit=edit: change_yaml(repo, MANIFEST, edit), "", "invalid manifest")

    def redirected_parent(repo: Path) -> None:
        path = repo / "roles/host_desktop_sway/files/palette"
        external = repo.parent / "external-palettes"
        path.rename(external)
        path.symlink_to(external, target_is_directory=True)
    refused_preview(redirected_parent, "", "redirected palette ancestor")

    def redirected_themes(repo: Path) -> None:
        path = repo / "themes"
        external = repo.parent / "external-themes"
        path.rename(external)
        path.symlink_to(external, target_is_directory=True)
    refused_preview(redirected_themes, "", "redirected manifest ancestor")

    def input_directory(repo: Path) -> None:
        path = repo / PALETTES["green"]
        path.unlink()
        path.mkdir()
    refused_preview(input_directory, "", "directory instead of palette")

    def input_fifo(repo: Path) -> None:
        path = repo / PALETTES["green"]
        path.unlink()
        os.mkfifo(path)
    refused_preview(input_fifo, "regular file", "FIFO instead of palette")
    print("HyperLab source runtime palette summaries contract: OK")


def main() -> int:
    require(THEME.is_file(), "trust-model manifest missing")
    require(TOOL.is_file(), "theme registry tool missing")
    require(bool(TOOL.stat().st_mode & 0o111),
            "theme registry tool is not executable")

    manifests = sorted((ROOT / "themes").glob("*/theme.yml"))

    require(
        [path.parent.name for path in manifests] == ["trust-model"],
        "scaffold must register exactly trust-model",
    )

    doc = yaml.safe_load(THEME.read_text(encoding="utf-8"))

    require(doc["version"] == 1, "manifest version drifted")
    require(doc["id"] == "trust-model", "theme id drifted")
    require(doc["status"] == "scaffold", "theme must remain scaffold")
    require(doc["selector"]["visible"] is False,
            "unfinished theme became selectable")

    expected_surfaces = {
        "quickshell": True,
        "gtk": True,
        "rofi": True,
        "lockscreen": True,
        "foot": True,
        "kitty": True,
        "wallpaper": True,
        "keyboard_rgb": True,
    }

    require(
        doc["surfaces"] == expected_surfaces,
        "theme surface ownership changed",
    )

    require(
        doc["wallpaper"] == {
            "policy": "trust-aware",
            "asset_set": "hyperlab-trust-v2",
        },
        "trust-model wallpaper policy changed",
    )

    rgb = doc["keyboard_rgb"]

    require(rgb["enabled"] is True, "theme RGB was disabled")
    require(rgb["mode"] == "trust", "trust-model RGB mode changed")
    require(
        rgb["provider"] == "hyperlab-nitro-control",
        "RGB escaped the reviewed broker",
    )
    require(rgb["capability"] == "per_zone",
            "RGB capability changed")
    require(rgb["zones"] == 4, "Nitro four-zone contract changed")
    require(rgb["brightness"] == "preserve",
            "theme unexpectedly forces keyboard brightness")
    require(
        rgb["unavailable"] == "continue-without-rgb",
        "non-RGB hardware fallback changed",
    )

    require(
        doc["trust"] == {
            "authority": "host-owned",
            "source": "hyperlab-trust-state",
            "appearance_binding": "dynamic",
            "identities": {
                "host": "neutral",
                "clean": "dom_clean",
                "dev": "dom_dev",
                "services": "dom_services",
                "dirty": "dom_dirty",
                "lab": "dom_lab",
            },
        },
        "trust-model authority or identities changed",
    )

    require(
        all(value is False for value in doc["security"].values()),
        "theme manifest relaxed its security boundary",
    )

    forbidden_keys = {
        "command",
        "commands",
        "exec",
        "execute",
        "shell",
        "sudo",
        "pkexec",
        "sysfs",
        "script",
    }

    def reject_forbidden_keys(value, location="theme"):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()

                require(
                    lowered not in forbidden_keys,
                    (
                        "executable theme primitive introduced: "
                        f"{location}.{key}"
                    ),
                )

                reject_forbidden_keys(
                    child,
                    f"{location}.{key}",
                )

        elif isinstance(value, list):
            for index, child in enumerate(value):
                reject_forbidden_keys(
                    child,
                    f"{location}[{index}]",
                )

    reject_forbidden_keys(doc)

    validation = subprocess.run(
        [
            "python3",
            str(TOOL),
            "--repo",
            str(ROOT),
            "validate",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    require(
        validation.returncode == 0,
        "registry validator failed:\n"
        + validation.stdout
        + validation.stderr,
    )

    listing = subprocess.run(
        [
            "python3",
            str(TOOL),
            "--repo",
            str(ROOT),
            "list",
            "--json",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    require(
        listing.returncode == 0,
        "registry JSON listing failed",
    )

    payload = json.loads(listing.stdout)

    require(payload["version"] == 1, "registry JSON version drifted")
    require(len(payload["themes"]) == 1,
            "registry JSON theme count changed")

    registered = payload["themes"][0]

    require(
        registered["id"] == "trust-model",
        "registry JSON selected wrong theme",
    )
    require(
        registered["keyboard_rgb"]["mode"] == "trust",
        "registry JSON lost RGB policy",
    )
    require(registered["status"] == "scaffold" and registered["visible"] is False,
            "registry JSON promoted the hidden scaffold")

    legacy = {"green", "violet", "blue", "red"}

    require(
        legacy.isdisjoint(
            {path.parent.name for path in manifests}
        ),
        "legacy palettes were registered as plugin themes",
    )

    check_legacy_installer(ROOT)
    check_palette_summaries()

    print("HyperLab declarative theme registry contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
