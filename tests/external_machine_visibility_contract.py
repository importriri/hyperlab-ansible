#!/usr/bin/env python3
"""One fixture inventory on the native shell and the GTK recovery surface."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
import io
import json
import os
import re
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import patch

import host_quickshell_runtime_contract as runtime
from recovery_gpu_ladder_contract import descendants, gtk_display, load_manager, run_gtk_worker

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/external-machines.json").read_text())

NATIVE = '''
            const raw = @@RAW@@;
            const product = sharedState.machines;
            function observe(rows) {
                sharedState.applyOutsideDomainsPayload(JSON.stringify({
                    machines_available: true, machines: rows }));
            }
            observe(raw);
            check(sharedState.machines.length === 3 && sharedState.outsideDomains.length === 4,
                  "the fixture populations merged or lost a domain");
            check(sharedState.machinesRunning === 1 && sharedState.managedMachinesRunning === 0
                  && sharedState.externalMachinesRunning === 1,
                  "running counts omitted or misclassified the external domain");
            sharedSurfaces.openWorkspace("machines");
            const stage = find(workspaceSurface, "machine-stage");
            check(stage !== null && stage.total === 7,
                  "Machines does not list all seven CLI domains");
            check(stage.groups.length === 1 && stage.groups[0].machines.length === 3,
                  "the managed group no longer contains its three Machines");
            for (const row of product)
                check(visibleText(stage, row.name), "a managed Machine is not rendered");
            check(find(stage, "machine-inventory-summary").subtitle.indexOf("0 managed running · 1 external running") >= 0,
                  "Machines summary omitted the external running count");
            check(find(stage, "external-machines-heading").label === "Not managed",
                  "external domains have no separate group");
            function checkExternal() {
                find(stage, "external-machine-list").forceLayout();
                for (const row of raw.filter(row => row.product_managed !== true)) {
                    const item = find(stage, "external-machine-" + row.name);
                    check(item !== null && item.visible,
                          "an external domain is missing from Machines");
                    if (item === null) continue;
                    check(item.color.a === 0 && item.border.width > 0
                          && item.border.color === sharedTheme.textSecondary,
                          "native external identity borrowed a colour or fill");
                    check(item.lifecycle === "external",
                          "an external row lost its explicit lifecycle");
                    function readOnly(node) {
                        check(node.activeFocusOnTab !== true && node.activated === undefined
                              && node.clicked === undefined && node.tapped === undefined,
                              "a native external row acquired an action");
                        for (let i = 0; i < node.children.length; i++) readOnly(node.children[i]);
                    }
                    readOnly(item);
                }
            }
            checkExternal();
            stage.layoutMode = "list";
            checkExternal();
            stage.query = "hl-lab-host";
            check(stage.filteredOutside.length === 1 && stage.filtered.length === 0,
                  "filtering cannot find an external machine");
            stage.query = "";
            stage.stateFilter = "running";
            check(stage.filteredOutside.length === 1,
                  "running filter omitted the external machine");
            stage.stateFilter = "all";
            sharedSurfaces.openWorkspacePage("controls", "session");
            const session = find(workspaceSurface, "session-running-summary");
            check(session !== null && session.description === "0 managed running · 1 external running",
                  "Session omitted the external running count");
            sharedSurfaces.openWorkspacePage("diagnostics", "inventory");
            check(find(workspaceSurface, "diagnostics-running-summary").value
                  === "0 managed running · 1 external running",
                  "Diagnostics omitted the external running count");
            // Actual runtime wins even when a product row reports drift.
            raw[0].state = "running";
            observe(raw);
            check(sharedState.machinesRunning === 2 && sharedState.managedMachinesRunning === 1,
                  "running managed drift was hidden by the product projection");
            raw[0].state = "shut off";
            sharedState.outsideDomainsObservedAt = Date.now() - 600000;
            check(sharedState.runningMachinesSummary.indexOf("Last observed") >= 0,
                  "a stale running count was presented as current");
            observe(raw);
            raw[3].state = "unknown";
            observe(raw);
            check(sharedState.runningMachinesSummary === "Running state unknown",
                  "an unreadable external state claimed a complete running count");
            raw[3].state = "running";
            observe(raw);
            // Duplicate, missing and malformed inputs never produce a zero claim.
            observe(raw.concat([raw[3]]));
            check(!sharedState.outsideDomainsAvailable,
                  "duplicated raw domain names were accepted");
            check(sharedState.runningMachinesSummary.indexOf("unavailable") >= 0,
                  "an unavailable raw inventory claimed a running count");
            observe(raw);
            sharedState.applyMachinePayload(JSON.stringify({
                machines_available: true, machines: product.concat([product[0]])}));
            check(!sharedState.machinesAvailable,
                  "duplicated product names were accepted");
            sharedState.applyMachinePayload(JSON.stringify({machines_available: true, machines: []}));
            check(sharedState.outsideDomains.length === 7 && sharedState.machinesRunning === 1,
                  "an empty product registry hid libvirt domains");
            sharedState.applyMachinePayload("not json");
            check(sharedState.outsideDomains.length === 7,
                  "unavailable product membership hid known raw domains");
            check(sharedState.runningMachinesSummary.indexOf("1 running") >= 0
                  && sharedState.runningMachinesSummary.indexOf("unavailable") >= 0,
                  "unavailable product membership hid known running domains");
            sharedState.applyOutsideDomainsPayload("not json");
            check(sharedState.runningMachinesSummary.indexOf("unavailable") >= 0,
                  "malformed inventory became zero running");
'''


def native() -> None:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    assert runner, "Qt 6 qmlscene is required for external Machine visibility"
    directory = runtime.stage()
    try:
        for width, height in ((1920, 1080), (800, 600)):
            body = NATIVE.replace("@@RAW@@", json.dumps(FIXTURE["managed"] + FIXTURE["external"]))
            source, messages = runtime.scenario_source(width, height, FIXTURE["managed"], body)
            runtime.run(runner, directory, "external-machines", source, messages)
    finally:
        shutil.rmtree(directory)


def recovery() -> int:
    with gtk_display() as gtk:
        namespace = load_manager(gtk)
        namespace.update(Path=Path, os=os, ThreadPoolExecutor=ThreadPoolExecutor, as_completed=as_completed)
        calls = []
        snapshots = []
        def cli(*args: str, **_kwargs: bool) -> dict | list:
            calls.append(args)
            if args == ("machine", "inventory"):
                return {"machines_available": True, "machines": FIXTURE["managed"]}
            if args == ("vm", "list"):
                return FIXTURE["managed"] + FIXTURE["external"]
            return {} if args == ("status",) else []
        namespace.update(run_cli_json=cli, GLib=SimpleNamespace(idle_add=lambda callback, model: callback(model)))
        reader = namespace["HyperlabWindow"]()
        reader._apply_model = snapshots.append
        reader._load_model()
        assert ("machine", "inventory") in calls, "GTK refresh does not read product inventory"
        assert snapshots[0].product_names == {row["name"] for row in FIXTURE["managed"]}
        window = namespace["HyperlabWindow"]()
        window.model = namespace["Model"](
            domains=copy.deepcopy(FIXTURE["managed"] + FIXTURE["external"]),
            product_inventory={"machines_available": True, "machines": FIXTURE["managed"]},
        )
        window.model.specs = [{"spec": {"name": row["name"], "network_profile": "dev"}}
                              for row in FIXTURE["managed"]]
        window.selected_vm = None
        window._grid_columns = {}
        assert len(window.model.running_domains) == 1
        expected = "0 managed running · 1 external running"
        assert window.model.running_summary == expected
        summary = window._system_summary_card()
        assert expected in [item.get_text() for item in descendants(summary)
                            if isinstance(item, gtk.Label)], "GTK summary omitted external running"
        window.drawer_holder = gtk.Box()
        window.header_title = gtk.Label()
        window.header_status = gtk.Label()
        window.current_section = "vms"
        window._rebuild_drawer()
        assert window.header_status.get_text() == expected, "GTK drawer count omitted external running"
        overview = window._build_overview()
        assert expected in [item.get_text() for item in descendants(overview)
                            if isinstance(item, gtk.Label)], "GTK Overview omitted external running"
        # An orphaned managed-machine metadata flag is not registry membership.
        orphan = window.model.domains[3]
        orphan["product_managed"] = True
        assert not window.model.is_product_domain(orphan), "GTK adopted an orphan metadata flag"
        assert window.model.running_summary == expected, "GTK counted an orphan as product managed"
        page = window._build_vm_showcase(columns=4)
        labels = [item.get_text() for item in descendants(page) if isinstance(item, gtk.Label)]
        assert all(row["name"] in labels for row in window.model.domains), "GTK hid a CLI domain"
        assert "Not managed" in labels, "GTK lost the external group"
        for row in FIXTURE["external"]:
            assert window._domain_for_vm(row) == "external", "GTK assigned trust without a reviewed spec"
            tile = window._mock_vm_tile(row)
            drawer = window._drawer_vm_row(row)
            assert not any(name.startswith("domain-badge-") for item in descendants(drawer)
                           for name in item.get_css_classes()), "GTK drawer borrowed attachment colour"
            assert drawer.has_css_class("vm-domain-external"), "GTK drawer lost its external identity"
            identity_widgets = [item for item in descendants(tile)
                                if any(name.startswith("vm-domain-") for name in item.get_css_classes())]
            assert identity_widgets and all(item.has_css_class("vm-domain-external")
                                            for item in identity_widgets), "GTK external domain borrowed a colour"
            assert any("external" in item.get_text() for item in descendants(tile)
                       if isinstance(item, gtk.Label)), "GTK external lifecycle is not visible"
        trusted = window.model.domains[0]
        assert window._domain_for_vm(trusted) == "dev", "a reviewed Machine lost its identity"
        for edits in ({"managed": False}, {"trust_profile": None}, {"networks": ["dirty"]}):
            assert window._domain_for_vm({**trusted, **edits}) == "external", "GTK classified drifting provenance"
        window.model.specs.append(copy.deepcopy(window.model.specs[0]))
        assert window._domain_for_vm(trusted) == "external", "GTK accepted duplicate specs"
        window.model.specs = []
        assert window._domain_for_vm({**FIXTURE["external"][0], "trust_profile": "dev",
                                      "network": "dev", "networks": ["dev"]}) == "external"
        unclassified = window._build_vm_showcase(columns=4)
        assert "Unclassified" in [item.get_text() for item in descendants(unclassified)
                                  if isinstance(item, gtk.Label)], "GTK lost its unclassified product group"
        for payload in ({}, {"machines_available": False, "machines": FIXTURE["managed"]},
                        {"machines_available": True, "machines": FIXTURE["managed"] * 2},
                        {"machines_available": True, "machines": [{"name": None}]}):
            window.model.product_inventory = payload
            assert window.model.product_names is None, "GTK accepted ambiguous product membership"
            assert window.model.running_summary == "1 running · managed membership unavailable"
        window.model.product_inventory = {"machines_available": True, "machines": FIXTURE["managed"]}
        window.model.load_errors = ["domains: fixture unreadable"]
        assert window.model.running_summary == "Running inventory unavailable"
        window.model.load_errors = []
        window.model.domains[3]["state"] = "unknown"
        assert window.model.running_summary == "Running state unknown", "GTK counted an unreadable state as stopped"
        for widget in (window._mock_vm_tile(window.model.domains[3]), window._drawer_vm_row(window.model.domains[3])):
            assert "UNKNOWN" in [item.get_text() for item in descendants(widget)
                                 if isinstance(item, gtk.Label)], "GTK rendered an unreadable state as stopped"
        window.model.domains[3]["state"] = "running"
        detail = gtk.Box()
        window._render_vm_detail(detail, FIXTURE["external"][0])
        assert any(isinstance(item, gtk.Button) and item.get_label() == "Shut down"
                   for item in descendants(detail)), "existing recovery shutdown was removed"
        # Parse the production stylesheet through GTK and inspect the external
        # identity rules separately from the appearance-only card material.
        css = gtk.CssProvider()
        css.load_from_data(namespace["CSS"].encode())
        # These are ordinary qualified CSS rules, without nested at-rules.
        # Parse selectors and declarations; do not treat comments as policy.
        source = re.sub(r"/\*.*?\*/", "", namespace["CSS"], flags=re.S)
        rules = [(selectors.strip().split(","), {
            key.strip(): value.strip() for entry in body.split(";")
            if ":" in entry for key, _, value in [entry.partition(":")]
        }) for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source)]
        external = [declarations for selectors, declarations in rules
                    if any(".vm-domain-external" in selector for selector in selectors)]
        assert external, "GTK has no external outline style"
        declarations = {key: value for rule in external for key, value in rule.items()}
        assert declarations["background"] == "transparent", "GTK filled the external identity"
        assert "@hl_text" in declarations["border"] and "dom_" not in str(declarations), \
            "GTK external identity borrowed a host or domain colour"
    print("External Machine recovery contract: OK")
    return 0


def main() -> int:
    # The fixture sent to both surfaces is exactly what vm list publishes.
    sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))
    from hyperlabctl.commands.vm import VmCommand
    domains = FIXTURE["managed"] + FIXTURE["external"]
    with patch("hyperlabctl.commands.vm.doc.build", return_value={"domains": domains}), \
            redirect_stdout(io.StringIO()) as output:
        assert VmCommand()._list(SimpleNamespace(json=True), object()) == 0
    assert json.loads(output.getvalue()) == domains, "surface fixture differs from CLI inventory"
    native()
    assert run_gtk_worker(Path(__file__)) == 0, "GTK external Machine contract failed"
    print("External Machine visibility contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(recovery() if "--gtk-worker" in sys.argv else main())
