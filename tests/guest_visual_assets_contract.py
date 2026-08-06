#!/usr/bin/env python3
"""Host-independent contracts for private guest wallpaper injection."""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import tempfile
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
THEMES = (
    "sakura-circuit",
    "neon-terminal",
    "moon-library",
    "glitch-lab",
)
SURFACES = ("desktop", "lockscreen")


def load_tool() -> ModuleType:
    path = ROOT / "tools/guest_assets.py"
    spec = importlib.util.spec_from_file_location("guest_assets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_bundle(root: Path) -> Path:
    sources = sorted(
        (ROOT / "roles/host_desktop_sway/files/wallpapers").glob("*/*.png")
    )
    assert len(sources) >= len(THEMES) * len(SURFACES)
    manifest: dict[str, object] = {"schema_version": 1, "themes": {}}
    source_index = 0
    for theme in THEMES:
        theme_data: dict[str, list[dict[str, str]]] = {}
        for surface in SURFACES:
            destination = root / "wallpapers" / theme / surface / "01.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sources[source_index], destination)
            source_index += 1
            theme_data[surface] = [
                {
                    "path": destination.relative_to(root).as_posix(),
                    "sha256": sha256(destination),
                }
            ]
        manifest["themes"][theme] = theme_data  # type: ignore[index]
    manifest_path = root / "guest-wallpapers.v1.yml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest_path


def test_bundle_validation_and_transactional_install() -> None:
    tool = load_tool()
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        source = work / "source"
        target = work / "target"
        source.mkdir()
        manifest = create_bundle(source)
        items = tool.validate_bundle(source, manifest)
        assert len(items) == 8

        stale = target / THEMES[0] / SURFACES[0] / "02.png"
        stale.parent.mkdir(parents=True)
        stale.write_bytes((source / items[0]["path"]).read_bytes())
        bootstrap = stale.parent / "bootstrap.png"
        bootstrap.write_bytes((source / items[1]["path"]).read_bytes())

        first = tool.install_bundle(source, manifest, target)
        assert first == {"changed": True, "files": 8, "themes": 4}
        assert not stale.exists()
        assert bootstrap.is_file()
        second = tool.install_bundle(source, manifest, target)
        assert second == {"changed": False, "files": 8, "themes": 4}


def test_bundle_refuses_tampering_and_unsafe_layouts() -> None:
    tool = load_tool()
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        source = work / "source"
        source.mkdir()
        manifest = create_bundle(source)
        data = yaml.safe_load(manifest.read_text())

        first = data["themes"][THEMES[0]][SURFACES[0]][0]
        original_path = first["path"]
        first["sha256"] = "0" * 64
        manifest.write_text(yaml.safe_dump(data, sort_keys=False))
        try:
            tool.validate_bundle(source, manifest)
        except tool.AssetError as error:
            assert "checksum mismatch" in str(error)
        else:
            raise AssertionError("tampered checksum was accepted")

        data = yaml.safe_load(create_bundle(source).read_text())
        first = data["themes"][THEMES[0]][SURFACES[0]][0]
        first["path"] = (
            f"wallpapers/{THEMES[0]}/{SURFACES[0]}/../desktop/01.png"
        )
        manifest.write_text(yaml.safe_dump(data, sort_keys=False))
        try:
            tool.validate_bundle(source, manifest)
        except tool.AssetError as error:
            assert "escapes" in str(error) or "must live" in str(error)
        else:
            raise AssertionError("escaping path was accepted")

        data = yaml.safe_load(create_bundle(source).read_text())
        desktop = data["themes"][THEMES[0]][SURFACES[0]][0]
        lockscreen = data["themes"][THEMES[0]][SURFACES[1]][0]
        lock_source = source / lockscreen["path"]
        desktop_source = source / desktop["path"]
        shutil.copyfile(desktop_source, lock_source)
        lockscreen["sha256"] = sha256(lock_source)
        manifest.write_text(yaml.safe_dump(data, sort_keys=False))
        try:
            tool.validate_bundle(source, manifest)
        except tool.AssetError as error:
            assert "distinct images" in str(error)
        else:
            raise AssertionError("shared desktop and lockscreen image was accepted")

        assert original_path.endswith("01.png")


def test_role_cleans_both_staging_locations() -> None:
    tasks = (ROOT / "roles/guest_visual_assets/tasks/main.yml").read_text()
    defaults = yaml.safe_load(
        (ROOT / "roles/guest_visual_assets/defaults/main.yml").read_text()
    )
    graph = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    playbook = yaml.safe_load((ROOT / "playbooks/guest-visual-assets.yml").read_text())

    assert defaults["guest_visual_assets_bundle_url"] == ""
    assert defaults["guest_visual_assets_bundle_sha256"] == ""
    assert "delegate_to: localhost" in tasks
    assert "XDG_RUNTIME_DIR" in tasks
    assert "checksum: \"sha256:{{ guest_visual_assets_bundle_sha256 }}\"" in tasks
    assert "Remove private remote asset staging" in tasks
    assert "Remove private controller asset staging" in tasks
    assert "brick_guard_brick: guest_visual_assets" in tasks
    assert graph["brick_requires"]["guest_visual_assets"] == [
        "guest_desktop_hyprland"
    ]
    assert graph["brick_playbooks"]["guest_visual_assets"] == (
        "playbooks/guest-visual-assets.yml"
    )
    assert playbook[0]["hosts"] == "workstations"


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"guest visual assets contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
