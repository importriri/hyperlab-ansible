#!/usr/bin/env python3
"""The Template review gate (ADR 0029).

A Template names its class, and the class bounds what it may offer: the
networks, the devices, the GPU handoff profiles, the lifecycles and Looking
Glass. One table in the Machine factory decides it; the factory's catalogue
and the repository's schema validator both apply it. This contract proves:

  1. every checked-in Template passes and its class matches its id;
  2. each class refuses what the roadmap's Template table forbids it;
  3. a Template cannot offer a GPU profile that none of its networks allows,
     while a services Template's GPU profiles are its own review;
  4. a gaming Template has exactly one network, so store accounts never
     share one with modded or offline games;
  5. the factory's catalogue fails closed on a Template outside its class.
"""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.errors import ContractError  # noqa: E402
from hyperlabctl.machine_factory import (  # noqa: E402
    TEMPLATE_CLASSES,
    template_catalog,
    template_class_problems,
)

PREFIXES = {"server-": "server", "workstation-": "workstation", "gaming-": "gaming",
            "svc-": "services", "browser-": "disposable"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def template(kind: str, networks: list[str], devices: dict, gpu: dict, lifecycles: dict,
             mode: str = "disabled") -> dict:
    return {
        "class": kind,
        "network_allowlist": networks,
        "device_capabilities": {"standard": True, "vfio": False, **devices},
        "gpu_handoff_profiles": {"clean": False, "dev": False, "dirty": False, "lab": False, **gpu},
        "lifecycles": {"permanent": False, "disposable": False, **lifecycles},
        "presentation": {"looking_glass_mode": mode},
    }


def refused(document: dict, expected: str) -> None:
    problems = template_class_problems(document)
    require(any(expected in problem for problem in problems),
            f"expected a refusal mentioning {expected!r}, got {problems!r}")


def check_repository() -> None:
    for path in sorted((ROOT / "templates").glob("*.yml")):
        data = yaml.safe_load(path.read_text())
        require(template_class_problems(data) == [], f"{path.name}: {template_class_problems(data)}")
        expected = next((kind for prefix, kind in PREFIXES.items() if data["id"].startswith(prefix)), None)
        require(expected == data["class"], f"{path.name}: class {data['class']} does not match its id")
    require(set(PREFIXES.values()) == set(TEMPLATE_CLASSES), "a class has no id prefix, or a prefix no class")


def check_classes() -> None:
    server = template("server", ["dev", "services", "lab"], {}, {}, {"permanent": True, "disposable": True})
    require(template_class_problems(server) == [], "a valid server Template was refused")
    refused(template("server", ["dev"], {"vfio": True}, {"dev": True}, {"permanent": True}),
            "a server Template cannot offer the vfio device")
    refused(template("server", ["clean"], {}, {}, {"permanent": True}),
            "a server Template cannot use the clean network")
    refused(template("server", ["dev"], {}, {}, {"permanent": True}, mode="linux-experimental"),
            "cannot present through Looking Glass")

    workstation = template("workstation", ["dev"], {"vfio": True}, {"dev": True, "dirty": True, "lab": True},
                           {"permanent": True}, mode="linux-experimental")
    require(template_class_problems(workstation) == [], "a valid workstation Template was refused")
    refused(template("workstation", ["dev", "dirty"], {}, {}, {"permanent": True}),
            "a workstation Template cannot use the dirty network")
    refused(template("workstation", ["dev"], {"vfio": True}, {"clean": True}, {"permanent": True}),
            "GPU profile clean is above the class of every network")

    clean = template("gaming", ["clean"], {"vfio": True}, {"clean": True}, {"permanent": True}, mode="windows")
    require(template_class_problems(clean) == [], "a valid gaming-clean Template was refused")
    refused(template("gaming", ["clean", "dirty"], {"vfio": True}, {"dirty": True}, {"permanent": True}),
            "exactly one network")
    refused(template("gaming", ["dirty"], {"vfio": True}, {"dev": True}, {"permanent": True}),
            "GPU profile dev is above the class of every network")
    refused(template("gaming", ["services"], {}, {}, {"permanent": True}),
            "a gaming Template cannot use the services network")

    services = template("services", ["services"], {"vfio": True}, {"clean": True, "dev": True},
                        {"permanent": True})
    require(template_class_problems(services) == [],
            "a services Template's GPU profiles are its own review, not a rung")
    refused(template("services", ["services", "dev"], {}, {}, {"permanent": True}),
            "a services Template cannot use the dev network")
    refused(template("services", ["services"], {"vfio": True}, {"dev": True}, {"permanent": True},
                     mode="linux-experimental"), "cannot present through Looking Glass")

    browser = template("disposable", ["dirty"], {}, {}, {"disposable": True})
    require(template_class_problems(browser) == [], "a valid disposable Template was refused")
    refused(template("disposable", ["dirty"], {}, {}, {"permanent": True, "disposable": True}),
            "a disposable Template cannot be permanent")
    refused(template("disposable", ["dirty"], {"vfio": True}, {"dirty": True}, {"disposable": True}),
            "a disposable Template cannot offer the vfio device")
    refused(template("disposable", ["dev"], {}, {}, {"disposable": True}),
            "a disposable Template cannot use the dev network")

    for kind in (None, "Workstation", "lab", ["server"]):
        document = template("server", ["dev"], {}, {}, {"permanent": True})
        document["class"] = kind
        refused(document, "is not one of")


def check_catalogue() -> None:
    with tempfile.TemporaryDirectory(prefix="hyperlab-template-gate-") as temporary:
        root = Path(temporary)
        for directory in ("images", "templates", "schemas"):
            (root / directory).mkdir()
        for path in (ROOT / "images").glob("*.yml"):
            (root / "images" / path.name).write_text(path.read_text())
        for path in (ROOT / "schemas").glob("*.yml"):
            (root / "schemas" / path.name).write_text(path.read_text())
        good = yaml.safe_load((ROOT / "templates/server-arch.yml").read_text())
        (root / "templates/server-arch.yml").write_text(yaml.safe_dump(good, sort_keys=False))
        bad = copy.deepcopy(good)
        bad["id"] = "server-wide"
        bad["network_allowlist"] = ["dev", "clean"]
        (root / "templates/server-wide.yml").write_text(yaml.safe_dump(bad, sort_keys=False))
        # Like any invalid Template, one outside its class fails the whole
        # catalogue closed rather than being offered or quietly dropped.
        try:
            template_catalog(root)
            outcome = "accepted"
        except ContractError as error:
            outcome = str(error)
        require("a server Template cannot use the clean network" in outcome,
                "the catalogue accepted a Template outside its class: %r" % outcome)
        (root / "templates/server-wide.yml").unlink()
        entries = {entry["id"]: entry for entry in template_catalog(root)}
        require("server-arch" in entries, "a valid Template is not offered")


def main() -> int:
    check_repository()
    check_classes()
    check_catalogue()
    print("Template review gate contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
