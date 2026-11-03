#!/usr/bin/env python3
"""Recovery GPU, network and Create readbacks use the CLI's trust provider."""
from __future__ import annotations

import ast
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, field
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))
from hyperlabctl.commands.trust import TrustCommand  # noqa: E402
from hyperlabctl.providers.trust import TrustProvider  # noqa: E402


def run_gtk_worker(script: Path) -> int:
    """Keep GTK's bundled display server alive until its worker has exited."""
    server = shutil.which("gtk4-broadwayd")
    assert server, "gtk4-broadwayd from GTK 4 is required for recovery layout allocation"
    with tempfile.TemporaryDirectory(prefix="hyperlab-gtk-") as directory:
        env = {**os.environ, "GDK_BACKEND": "broadway", "BROADWAY_DISPLAY": ":0",
               "XDG_RUNTIME_DIR": directory, "GSETTINGS_BACKEND": "memory",
               "GTK_A11Y": "none", "GSK_RENDERER": "cairo",
               "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent"}
        # Both the GTK client socket and Broadway's HTTP socket stay private.
        # No browser, TCP listener or physical desktop session is needed.
        with subprocess.Popen(
            [server, "--unixsocket", str(Path(directory) / "http.socket"), ":0"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        ) as process:
            try:
                deadline = time.monotonic() + 10
                while not (Path(directory) / "broadway1.socket").is_socket():
                    assert process.poll() is None, "private GTK display server exited before startup"
                    assert time.monotonic() < deadline, "private GTK display server did not start"
                    time.sleep(0.01)
                return subprocess.run(
                    [sys.executable, str(script), "--gtk-worker"], check=False, timeout=30,
                    env=env,
                ).returncode
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


@contextmanager
def gtk_display() -> Iterator[Any]:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    yield Gtk


def load_manager(gtk: Any) -> dict[str, Any]:
    """Execute production builders without its application or hardware imports."""
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__" or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in {"DOMAIN_META", "CSS"}
                for target in node.targets) or isinstance(node, ast.FunctionDef) and node.name in {
                "clear_box", "set_css", "text_label", "dropdown_value"}:
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in {"Model", "HyperlabWindow"}:
            if node.name == "HyperlabWindow":
                node.bases = []
                node.body = [member for member in node.body
                             if not isinstance(member, ast.FunctionDef) or member.name != "__init__"]
            nodes.append(node)
    namespace = {"Gtk": gtk, "dataclass": dataclass, "field": field}
    exec(compile(ast.Module(nodes, type_ignores=[]), str(MANAGER), "exec"), namespace)
    return namespace


def descendants(widget: Any) -> Iterator[Any]:
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from descendants(child)
        child = child.get_next_sibling()


def kv(widget: Any) -> dict[str, str]:
    return {row.get_first_child().get_text(): row.get_last_child().get_text()
            for row in descendants(widget) if row.has_css_class("kv-row")}


def cli_ladder(levels: dict[str, int]) -> dict[str, Any]:
    ctx = SimpleNamespace(config=SimpleNamespace(var=lambda key, default: levels),
                          read_text=lambda path: "2")
    ctx.config.gpu_handoff_state = Path("unused-fixture-trust")
    trust = TrustProvider().collect(ctx)
    with patch("hyperlabctl.commands.trust.doc.build", return_value={"trust": trust}), redirect_stdout(io.StringIO()) as out:
        assert TrustCommand().run(SimpleNamespace(json=True), ctx) == 0
    return {"provider": trust, "cli": json.loads(out.getvalue())["ladder"]}


def main() -> int:
    levels = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())["gpu_trust_levels"]
    with gtk_display() as gtk:
        namespace = load_manager(gtk)
        window = namespace["HyperlabWindow"]()
        window.inspect_holder = gtk.Box()
        for ladder in (levels, {name: 3 - rank for name, rank in levels.items()}):
            source = cli_ladder(ladder)
            window.model = namespace["Model"](
                status={"trust": source["provider"], "gpu": {"owner": "fixture-owner"}},
                domains=[{"name": "fixture-owner", "network": "services", "gpu_trust_profile": "dev"}],
            )
            page = window._build_gpu()
            rungs = [item for item in descendants(page) if item.has_css_class("gpu-rung")]
            actual = [(rung.get_first_child().get_text(), rung.get_first_child().get_next_sibling().get_first_child().get_text().lower())
                      for rung in rungs]
            expected = [(str(row["level"]), row["name"]) for row in source["cli"]]
            assert actual == expected, f"recovery GPU ladder differs from CLI: {actual} != {expected}"
            current = [rung.get_first_child().get_next_sibling().get_first_child().get_text().lower()
                       for rung in rungs if rung.has_css_class("current")]
            assert current == ["dev"], "GPU owner was ranked by its network instead of its handoff profile"
            for name in namespace["DOMAIN_META"]:
                dock = gtk.Box()
                window._populate_network_dock(dock, name)
                dropdown = gtk.DropDown.new_from_strings([name])
                window.create_widgets = {"network": dropdown}
                window._populate_create_inspector()
                expected_rank = str(ladder[name]) if name in ladder else "Outside GPU ladder"
                for surface in (dock, window.inspect_holder):
                    assert kv(surface)["GPU rank"] == expected_rank, f"{name}: recovery rank differs from CLI"
        for status in ({}, {"trust": None}, {"trust": {"ladder": {}}},
                       {"trust": {"ladder": {**levels, "dev": True}}},
                       {"trust": {"ladder": {**levels, "lab": levels["dev"]}}},
                       {"trust": {"ladder": {**levels, "services": 4}}}):
            window.model = namespace["Model"](status=status)
            assert not any(item.has_css_class("gpu-rung") for item in descendants(window._build_gpu())), "unavailable ladder was replaced by invented ranks"
            dock = gtk.Box()
            window._populate_network_dock(dock, "dev")
            assert kv(dock)["GPU rank"] == "Unknown", "unknown rank became a default"
    print("Recovery GPU ladder contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() if "--gtk-worker" in sys.argv else run_gtk_worker(Path(__file__)))
