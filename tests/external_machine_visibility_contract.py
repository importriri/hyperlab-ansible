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
import shlex
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import host_quickshell_runtime_contract as runtime
from recovery_gpu_ladder_contract import descendants, gtk_display, load_manager, run_gtk_worker

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/external-machines.json").read_text())
PRODUCT = set(FIXTURE["product"])


def inventory() -> tuple[list[dict], dict, list[dict]]:
    """Build every surface input from minimal libvirt facts, not row shapes.

    The fake host runs the real domains provider. `vm list` and
    `waybar --field vms` print what the installed CLI prints; product rows
    extend the same machine card with registry fields, as `machine
    inventory` does for a matching runtime.
    """
    sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))
    sys.path.append(str(ROOT / "tools/hyperlabctl/tests"))
    import world
    from hyperlabctl.commands.vm import VmCommand
    from hyperlabctl.commands.waybar import WaybarCommand
    facts = [{**row, "metadata": world.managed_metadata(row["network"], product_machine=True)}
             if row["name"] in PRODUCT else row for row in FIXTURE["domains"]]
    ctx = world.build(domains=facts)
    with redirect_stdout(io.StringIO()) as listed:
        assert VmCommand()._list(SimpleNamespace(json=True), ctx) == 0
    with redirect_stdout(io.StringIO()) as observed:
        assert WaybarCommand().run(SimpleNamespace(field="vms"), ctx) == 0
    vm_list, raw = json.loads(listed.getvalue()), json.loads(observed.getvalue())
    assert [row["name"] for row in vm_list] == [row["name"] for row in FIXTURE["domains"]]
    assert sorted(row["name"] for row in raw["machines"]) == sorted(row["name"] for row in vm_list)
    product = [{**card, "product_managed": True, "display_name": card["name"],
                "network_profile": card["network"], "runtime_present": True,
                "runtime_drift": False}
               for card in raw["machines"] if card["name"] in PRODUCT]
    assert len(product) == len(PRODUCT), "a product Machine has no runtime row"
    return vm_list, raw, product

NATIVE = '''
            const raw = @@RAW@@;
            const product = sharedState.machines;
            const productNames = new Set(product.map(row => row.name));
            const outside = raw.filter(row => !productNames.has(row.name));
            const hostIndex = raw.findIndex(row => row.name === "hl-lab-host");
            const firstIndex = raw.findIndex(row => row.name === "development-01");
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
            // The CLI may still report a GPU-gate provenance for an unmanaged
            // domain; the shell never turns it into an identity.
            observe(raw.map(row => row.name === "hl-lab-host"
                ? Object.assign({}, row, {"provenance": "dev"}) : row));
            check(sharedState.outsideDomains.length === 4
                  && sharedState.outsideDomains.every(row => row.provenance === "unclassified"),
                  "a CLI provenance classified a domain outside the registry");
            observe(raw);
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
            function checkReadOnly(rows, lifecycle, caption) {
                const list = find(stage, "external-machine-list");
                list.forceLayout();
                for (let index = 0; index < rows.length; index++) {
                    const row = rows[index];
                    list.positionViewAtIndex(index, ListView.Beginning);
                    list.forceLayout();
                    const item = find(stage, "external-machine-" + row.name);
                    check(item !== null && item.visible,
                          "an external domain is missing from Machines");
                    if (item === null) continue;
                    check(item.color.a === 0 && item.border.width > 0
                          && item.border.color === sharedTheme.textSecondary,
                          "native external identity borrowed a colour or fill");
                    check(item.lifecycle === lifecycle,
                          "a read-only row has the wrong membership lifecycle");
                    check(visibleText(item, caption + " · " + stage.icons.machineStateWord(row.state)),
                          "a read-only row has the wrong membership caption");
                    // `data` holds children and resources: pointer handlers,
                    // MouseAreas and buttons all fail, wherever they hang.
                    function readOnly(node) {
                        check(node.activeFocusOnTab !== true
                              && node.activated === undefined && node.clicked === undefined
                              && node.tapped === undefined && node.pressed === undefined
                              && node.grabPermissions === undefined,
                              "a native external row acquired an action");
                        const owned = node.data !== undefined ? node.data : [];
                        for (let i = 0; i < owned.length; i++) readOnly(owned[i]);
                    }
                    readOnly(item);
                    check(sharedState.machineById(row.name) === null,
                          "a read-only row resolves to an operational Machine");
                }
            }
            checkReadOnly(outside, "external", "external");
            stage.layoutMode = "list";
            checkReadOnly(outside, "external", "external");
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
            let sessionView = session;
            while (sessionView && typeof sessionView.dangerConsequence !== "function")
                sessionView = sessionView.parent;
            for (const action of ["session-poweroff", "session-reboot", "session-logout"])
                check(sessionView && sessionView.dangerConsequence(action)
                      .indexOf("0 managed running · 1 external running") >= 0,
                      "a session confirmation consequence omitted the external running count");
            sharedSurfaces.openWorkspacePage("diagnostics", "inventory");
            check(find(workspaceSurface, "diagnostics-running-summary").value
                  === "0 managed running · 1 external running",
                  "Diagnostics omitted the external running count");
            // Actual runtime wins even when a product row reports drift.
            raw[firstIndex].state = "running";
            observe(raw);
            check(sharedState.machinesRunning === 2 && sharedState.managedMachinesRunning === 1,
                  "running managed drift was hidden by the product projection");
            raw[firstIndex].state = "shut off";
            sharedState.outsideDomainsObservedAt = Date.now() - 600000;
            check(sharedState.runningMachinesSummary.indexOf("Last observed") >= 0,
                  "a stale running count was presented as current");
            observe(raw);
            // A stale registry read keeps its own age beside the defined count.
            sharedState.machinesObservedAt = Date.now() - 600000;
            check(stage.inventoryState === "stale"
                  && find(stage, "machine-inventory-summary").subtitle.indexOf("last observed") >= 0,
                  "a stale product inventory lost its last observed age");
            sharedState.applyMachinePayload(JSON.stringify({machines_available: true, machines: product}));
            raw[hostIndex].state = "unknown";
            observe(raw);
            check(sharedState.runningMachinesSummary === "Running state unknown",
                  "an unreadable external state claimed a complete running count");
            raw[hostIndex].state = "running";
            observe(raw);
            // Duplicate, missing and malformed inputs never produce a zero claim.
            observe(raw.concat([raw[hostIndex]]));
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
            sharedSurfaces.openWorkspace("machines");
            function firstGuidance(node) {
                if (node.title === "No Machines yet") return node;
                for (let index = 0; index < node.children.length; index++) {
                    const found = firstGuidance(node.children[index]);
                    if (found) return found;
                }
                return null;
            }
            observe(outside);
            const guidance = firstGuidance(stage);
            check(guidance && guidance.visible
                  && sharedState.outsideDomains.length === 4
                  && find(stage, "external-machines-heading").visible,
                  "an empty registry with external domains lost first-Machine guidance");
            check(guidance.description.indexOf("Not managed") >= 0,
                  "first-Machine guidance omitted the existing external group");
            observe([]);
            check(guidance.visible && guidance.description.indexOf("Not managed") < 0,
                  "empty guidance claims domains appear below when none exist");
            observe(raw);
            sharedState.applyMachinePayload("not json");
            check(sharedState.outsideDomains.length === 7,
                  "unavailable product membership hid known raw domains");
            check(find(stage, "external-machines-heading").label
                  === "Observed domains · membership unavailable",
                  "unavailable membership defaulted to Not managed");
            check(find(stage, "external-machines-heading").description.indexOf("external") < 0,
                  "unavailable group description claimed external membership");
            check(sharedState.outsideDomains.every(row => row.lifecycle === "unknown"),
                  "unavailable membership defaulted to external lifecycle");
            checkReadOnly(raw, "unknown", "membership unknown");
            check(sharedState.runningMachinesSummary.indexOf("1 running") >= 0
                  && sharedState.runningMachinesSummary.indexOf("unavailable") >= 0,
                  "unavailable product membership hid known running domains");
            sharedSurfaces.openWorkspacePage("diagnostics", "inventory");
            check(visibleText(workspaceSurface, "Observed domains · membership unavailable"),
                  "Diagnostics defaulted unavailable membership to outside product inventory");
            for (const row of sharedState.outsideDomains)
                check(sharedState.outsideDomainKind(row) === "Membership unknown",
                      "Diagnostics inferred membership without the registry");
            sharedState.applyMachinePayload(JSON.stringify({machines_available: true, machines: product}));
            check(sharedState.outsideDomains.length === 4
                  && sharedState.outsideDomains.every(row => row.lifecycle === "external"),
                  "membership did not recover after the registry became readable");
            sharedState.applyOutsideDomainsPayload("not json");
            check(sharedState.runningMachinesSummary.indexOf("unavailable") >= 0,
                  "malformed inventory became zero running");
            // Without the raw read the total is partial and says so.
            sharedSurfaces.openWorkspace("machines");
            const partial = find(stage, "machine-inventory-summary").subtitle;
            check(partial.indexOf("3 managed · other domains unavailable") >= 0
                  && partial.indexOf("defined") < 0,
                  "Machines presented a partial total as every defined domain");
            sharedSurfaces.openWorkspacePage("diagnostics", "inventory");
            const definedRow = find(workspaceSurface, "diagnostics-defined-summary");
            check(definedRow !== null && definedRow.value === "3 managed · other domains unavailable",
                  "Diagnostics presented a partial total as every defined domain");
'''


def native() -> None:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    assert runner, "Qt 6 qmlscene is required for external Machine visibility"
    _vm_list, raw, product = inventory()
    directory = runtime.stage()
    try:
        for width, height in ((1920, 1080), (800, 600)):
            body = NATIVE.replace("@@RAW@@", json.dumps(raw["machines"]))
            source, messages = runtime.scenario_source(width, height, product, body)
            runtime.run(runner, directory, "external-machines", source, messages)
    finally:
        shutil.rmtree(directory)


def recovery() -> int:
    with gtk_display() as gtk:
        namespace = load_manager(gtk)
        namespace.update(Path=Path, os=os, ThreadPoolExecutor=ThreadPoolExecutor, as_completed=as_completed)
        vm_list, _raw, product = inventory()
        calls = []
        snapshots = []
        def cli(*args: str, **_kwargs: bool) -> dict | list:
            calls.append(args)
            if args == ("machine", "inventory"):
                return {"machines_available": True, "machines": product}
            if args == ("vm", "list"):
                return vm_list
            return {} if args == ("status",) else []
        namespace.update(run_cli_json=cli, GLib=SimpleNamespace(idle_add=lambda callback, model: callback(model)))
        reader = namespace["HyperlabWindow"]()
        reader._apply_model = snapshots.append
        reader._load_model()
        assert ("machine", "inventory") in calls, "GTK refresh does not read product inventory"
        assert snapshots[0].product_names == PRODUCT
        window = namespace["HyperlabWindow"]()
        window.model = namespace["Model"](
            domains=copy.deepcopy(vm_list),
            product_inventory={"machines_available": True, "machines": product},
        )
        # The `compose list` row shape: path, spec and the image entry.
        window.model.specs = [{"path": "vm-specs/%s.yml" % name, "image": {"id": "arch"},
                               "spec": {"name": name, "network_profile": "dev", "image": "arch"}}
                              for name in sorted(PRODUCT)]
        by_name = {row["name"]: row for row in window.model.domains}
        host = by_name["hl-lab-host"]
        outside = [row for row in window.model.domains if row["name"] not in PRODUCT]
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
        orphan = host
        orphan["product_managed"] = True
        assert not window.model.is_product_domain(orphan), "GTK adopted an orphan metadata flag"
        assert window.model.running_summary == expected, "GTK counted an orphan as product managed"
        page = window._build_vm_showcase(columns=4)
        labels = [item.get_text() for item in descendants(page) if isinstance(item, gtk.Label)]
        assert all(row["name"] in labels for row in window.model.domains), "GTK hid a CLI domain"
        assert "Not managed" in labels, "GTK lost the external group"
        header_labels = [item for item in descendants(page)
                         if isinstance(item, gtk.Label) and item.get_text() == "Not managed"]
        assert len(header_labels) == 1, "GTK duplicated the external group header"
        dot = header_labels[0].get_prev_sibling()
        assert isinstance(dot, gtk.Box) and dot.has_css_class("external-outline") \
            and not any(name.startswith("domain-dot-") for name in dot.get_css_classes()), \
            "GTK external group header borrowed a trust colour"

        def detail_lifecycle(row: dict) -> str:
            detail = gtk.Box()
            window._render_vm_detail(detail, row)
            keys = [item for item in descendants(detail)
                    if isinstance(item, gtk.Label) and item.has_css_class("kv-key")
                    and item.get_text() == "lifecycle"]
            assert len(keys) == 1, "GTK detail lost its lifecycle field"
            return keys[0].get_next_sibling().get_text()

        assert detail_lifecycle(by_name["development-01"]) == "permanent"
        assert detail_lifecycle(host) == "external"
        for row in outside:
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
        trusted = by_name["development-01"]
        assert window._domain_for_vm(trusted) == "dev", "a reviewed Machine lost its identity"
        for edits in ({"managed": False}, {"trust_profile": None}, {"networks": ["dirty"]}):
            assert window._domain_for_vm({**trusted, **edits}) == "external", "GTK classified drifting provenance"

        def identity_words(widget: object, css_class: str) -> list[str]:
            return [item.get_text() for item in descendants(widget)
                    if isinstance(item, gtk.Label) and item.has_css_class(css_class)]

        # A registry Machine without an identity is unclassified, never external.
        drifted = {**trusted, "trust_profile": None}
        facts = identity_words(window._mock_vm_tile(drifted), "vm-facts")
        # The neutral state badge shares the outline class; the identity
        # badge is the other outlined word.
        badges = [text for text in identity_words(window._drawer_vm_row(drifted), "external-outline")
                  if text not in ("RUNNING", "STOPPED", "UNKNOWN")]
        detail = gtk.Box()
        window._render_vm_detail(detail, drifted)
        subtitles = identity_words(detail, "inspect-subtitle")
        assert facts and badges and subtitles and all(
            "unclassified" in text and "external" not in text
            for text in facts + badges + subtitles), \
            "GTK called a product Machine external: %r" % (facts + badges + subtitles)
        # A leftover generated spec is not review: outside the registry, a
        # matching spec, network and trust profile still give no colour.
        generated = {**host, "managed": True, "trust_profile": "dev", "network": "dev",
                     "networks": ["dev"], "product_managed": False}
        window.model.specs.append({"path": "vm-specs/.generated/hl-lab-host.yml",
                                   "spec": {"name": "hl-lab-host", "network_profile": "dev"}})
        assert window._domain_for_vm(generated) == "external", "GTK coloured a non-product domain"
        assert all(item.has_css_class("vm-domain-external") for item in descendants(window._mock_vm_tile(generated))
                   if any(name.startswith("vm-domain-") for name in item.get_css_classes())), \
            "GTK tile coloured a non-product domain from a generated spec"
        window.model.specs.pop()
        # Segment attachment is not identity: every attached domain is counted,
        # and one without the segment identity is drawn as an outline.
        window.selected_network = "dev"
        window.inspect_holder = None
        policies = window._build_policies()
        attached = sorted(row["name"] for row in window.model.domains if "dev" in (row.get("networks") or []))
        assert "arch-dev" in attached and len(attached) == 5
        assert "%d machines · DHCP libvirt" % len(attached) in identity_words(policies, "network-node-sub"), \
            "GTK DEV segment lost a domain attached to its network"
        members = [item for item in descendants(policies)
                   if isinstance(item, gtk.Box) and item.has_css_class("network-member")]
        names = {identity_words(item, "network-member-name")[0]: item for item in members}
        assert sorted(names) == attached, "GTK DEV segment dock lost an attached domain"
        legacy = [item for item in descendants(names["arch-dev"])
                  if isinstance(item, gtk.Label) and item.has_css_class("external-outline")]
        assert legacy and legacy[0].get_text() == "external" and not any(
            name.startswith(("domain-", "vm-domain-")) and name != "vm-domain-external"
            for item in descendants(names["arch-dev"]) for name in item.get_css_classes()), \
            "GTK DEV segment gave an attached external domain the segment colour"
        window.model.specs.append(copy.deepcopy(window.model.specs[0]))
        assert window._domain_for_vm(trusted) == "external", "GTK accepted duplicate specs"
        window.model.specs = []
        assert window._domain_for_vm({**host, "trust_profile": "dev",
                                      "network": "dev", "networks": ["dev"]}) == "external"
        unclassified = window._build_vm_showcase(columns=4)
        assert "Unclassified" in [item.get_text() for item in descendants(unclassified)
                                  if isinstance(item, gtk.Label)], "GTK lost its unclassified product group"
        window.model.specs = [{"spec": {"name": name, "network_profile": "dev",
                                       "lifecycle": "permanent"}} for name in sorted(PRODUCT)]
        for payload in ({}, {"machines_available": False, "machines": product},
                        {"machines_available": True, "machines": product * 2},
                        {"machines_available": True, "machines": [{"name": None}]}):
            window.model.product_inventory = payload
            assert window.model.product_names is None, "GTK accepted ambiguous product membership"
            assert window.model.running_summary == "1 running · managed membership unavailable"
            observed = window._build_vm_showcase(columns=4)
            labels = [item.get_text() for item in descendants(observed) if isinstance(item, gtk.Label)]
            assert "Not managed" not in labels \
                and "Observed domains · membership unavailable" in labels, \
                "GTK unavailable membership defaulted to Not managed"
            assert all(row["name"] in labels for row in window.model.domains), \
                "GTK unavailable membership hid known raw domains"
            for row in window.model.domains:
                assert detail_lifecycle(row) == "unknown", \
                    "GTK unavailable membership defaulted to external detail lifecycle"
                for widget, css_class in ((window._mock_vm_tile(row), "vm-facts"),
                                          (window._drawer_vm_row(row), "caption")):
                    captions = [item.get_text() for item in descendants(widget)
                                if isinstance(item, gtk.Label) and item.has_css_class(css_class)]
                    assert captions and all("membership unknown" in caption for caption in captions), \
                        "GTK unavailable membership defaulted to external row lifecycle"
        window.model.product_inventory = {"machines_available": True, "machines": product}
        restored = window._build_vm_showcase(columns=4)
        assert "Not managed" in [item.get_text() for item in descendants(restored) if isinstance(item, gtk.Label)]
        assert detail_lifecycle(by_name["development-01"]) == "permanent", "GTK membership did not recover"
        window.model.load_errors = ["domains: fixture unreadable"]
        assert window.model.running_summary == "Running inventory unavailable"
        window.model.load_errors = []
        host["state"] = "unknown"
        assert window.model.running_summary == "Running state unknown", "GTK counted an unreadable state as stopped"
        for widget in (window._mock_vm_tile(host), window._drawer_vm_row(host)):
            assert "UNKNOWN" in [item.get_text() for item in descendants(widget)
                                 if isinstance(item, gtk.Label)], "GTK rendered an unreadable state as stopped"
        host["state"] = "running"
        host["product_managed"] = None
        detail = gtk.Box()
        window._render_vm_detail(detail, host)
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


def waybar_pill(raw: dict, product: list[dict]) -> None:
    """Run the bar's real VM pill argv through the real bridge, CLI stubbed."""
    config = json.loads(re.sub(r"(?m)^\s*//.*$", "", (
        ROOT / "roles/host_desktop_sway/files/waybar.jsonc").read_text(encoding="utf-8")))
    argv = shlex.split(config["custom/hyperlab-vms"]["exec"])
    assert argv[0] == "/usr/local/bin/privatestack-hyperlab", "the VM pill bypasses the bridge"
    source = (ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab.sh").read_text(encoding="utf-8")
    needle = "declare -r cli=/usr/local/bin/hyperlabctl"
    assert source.count(needle) == 1, "the bridge fixture cannot isolate hyperlabctl"
    # What each CLI read prints on the fixture host. The product inventory
    # counts only registry Machines, which is the defect being guarded.
    answers = {"waybar --field vms": raw,
               "machine inventory --json": {"text": "0/%d" % len(product), "class": "ok",
                                            "machines_available": True, "machines": product}}
    with tempfile.TemporaryDirectory(prefix="hyperlab-vm-pill-") as directory:
        cli = Path(directory) / "hyperlabctl"
        trace = Path(directory) / "trace.jsonl"
        cli.write_text("#!%s\nimport json, os, sys\n"
                       "with open(os.environ['PILL_TRACE'], 'a') as stream:\n"
                       "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                       "answers = json.loads(os.environ['PILL_ANSWERS'])\n"
                       "key = ' '.join(sys.argv[1:])\n"
                       "sys.exit(1) if key not in answers else print(json.dumps(answers[key]))\n"
                       % sys.executable)
        cli.chmod(0o700)
        bridge = Path(directory) / "bridge.sh"
        bridge.write_text(source.replace(needle, "declare -r cli=" + shlex.quote(str(cli))))
        result = subprocess.run(["bash", str(bridge), *argv[1:]], capture_output=True, text=True,
                                timeout=30, check=True,
                                env={**os.environ, "PILL_TRACE": str(trace),
                                     "PILL_ANSWERS": json.dumps(answers)})
        calls = [json.loads(line) for line in trace.read_text().splitlines()]
    payload = json.loads(result.stdout)
    assert calls == [["waybar", "--field", "vms"]], "the VM pill does not read every libvirt domain"
    assert payload["text"] == "1/%d" % len(FIXTURE["domains"]), \
        "the VM pill does not count the running external domain"
    assert "hl-lab-host  running" in payload["tooltip"].splitlines(), \
        "the VM pill tooltip hides the running external domain"


def main() -> int:
    _vm_list, raw, product = inventory()
    waybar_pill(raw, product)
    native()
    assert run_gtk_worker(Path(__file__)) == 0, "GTK external Machine contract failed"
    print("External Machine visibility contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(recovery() if "--gtk-worker" in sys.argv else main())
