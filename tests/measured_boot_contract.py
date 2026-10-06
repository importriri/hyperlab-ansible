#!/usr/bin/env python3
"""The measured boot image mirrors the boot entries and replaces nothing
it cannot prove (ADR 0044).

  1. each UKI profile carries exactly the command line of the type 1 entry
     it mirrors (the entry's options lines joined in order), with a unique
     id the builder accepts;
  2. the builder, run with fake ukify and sbctl, builds one profile per
     entry, joins them into one image with signed PCR 11 policies for the
     enter-initrd phase, signs it, and checks the signature before it
     replaces the image in use, which it keeps as the previous build; an
     unverified image never replaces it; a malformed configuration is
     refused before anything is built;
  3. the role is off by default, removes its rebuild hook while off, makes
     the PCR signing key once and keeps it private, and never touches the
     default entry, the LUKS key slots or the firmware's keys.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/measured_boot"
TOOL = ROLE / "files/hyperlab-uki-build.py"
SAMPLE = {
    "vfio_boot_luks_uuid": "0d1a6f34-1c2b-4c5d-8e9f-a0b1c2d3e4f5",
    "measured_boot_luks_uuid": "0d1a6f34-1c2b-4c5d-8e9f-a0b1c2d3e4f5",
    "luks_mapper_name": "cryptroot",
    "root_subvol": "@",
    "hardware_probe_vfio_ids_csv": "10de:2520,10de:228e",
    "kernel_name": "linux-hardened",
    "measured_boot_esp": "/boot",
    "measured_boot_key_dir": "/etc/hyperlab/uki",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def environment() -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True,
                             extensions=["jinja2.ext.do"])
    env.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(pattern, replacement, value)
    env.filters["to_nice_json"] = lambda value: json.dumps(value, indent=4)
    return env


def check_profiles() -> list[dict]:
    profiles = yaml.safe_load((ROOT / "roles/vfio_boot/defaults/main.yml").read_text())["vfio_boot_profiles"]
    env = environment()
    config = json.loads(env.from_string((ROLE / "templates/uki.json.j2").read_text()).render(
        vfio_boot_profiles=profiles, **SAMPLE))
    entry = env.from_string((ROOT / "roles/vfio_boot/templates/entry.conf.j2").read_text())
    require(len(config["profiles"]) == len(profiles), "a boot entry has no UKI profile")
    ids = [p["id"] for p in config["profiles"]]
    require(len(set(ids)) == len(ids) and all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", i) for i in ids),
            f"UKI profile ids are not unique and valid: {ids}")
    for item, profile in zip(profiles, config["profiles"]):
        rendered = entry.render(item=item, **SAMPLE)
        options = " ".join(line.split(None, 1)[1] for line in rendered.splitlines() if line.startswith("options "))
        require(profile["cmdline"] == options, f"{item['file']}: the UKI command line differs from the entry's")
        require(profile["title"] == item["title"], f"{item['file']}: the UKI profile has another title")
    require(config["kernel"] == "/boot/vmlinuz-linux-hardened"
            and config["initrd"] == "/boot/initramfs-linux-hardened.img", "the UKI uses another kernel")
    return config["profiles"]


FAKE_UKIFY = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(["ukify", *sys.argv[1:]]) + "\\n")
out = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--output="))
Path(out).write_text("uki")
"""

FAKE_SBCTL = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(["sbctl", *sys.argv[1:]]) + "\\n")
"""

FAKE_SBVERIFY = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(["sbverify", *sys.argv[1:]]) + "\\n")
sys.exit(1 if os.environ.get("FAKE_UNSIGNED") else 0)
"""


def run_tool(base: Path, config: dict, unsigned: bool = False) -> tuple[subprocess.CompletedProcess, list]:
    (base / "uki.json").write_text(json.dumps(config))
    log = base / "calls.jsonl"
    log.write_text("")
    env = dict(os.environ, HYPERLAB_UKI_CONFIG=str(base / "uki.json"), HYPERLAB_UKIFY=str(base / "ukify"),
               HYPERLAB_SBCTL=str(base / "sbctl"), HYPERLAB_SBVERIFY=str(base / "sbverify"), FAKE_LOG=str(log))
    if unsigned:
        env["FAKE_UNSIGNED"] = "1"
    result = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, env=env, check=False)
    return result, [json.loads(line) for line in log.read_text().splitlines()]


def check_builder(profiles: list[dict]) -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for name, source in (("ukify", FAKE_UKIFY), ("sbctl", FAKE_SBCTL), ("sbverify", FAKE_SBVERIFY)):
            (base / name).write_text(source)
            (base / name).chmod(0o755)
        esp = base / "esp"
        esp.mkdir()
        for name in ("vmlinuz", "initramfs.img", "pcr-private.pem", "pcr-public.pem", "db.pem"):
            (base / name).write_text(name)
        config = {"kernel": str(base / "vmlinuz"), "initrd": str(base / "initramfs.img"), "esp": str(esp),
                  "pcr_private_key": str(base / "pcr-private.pem"), "pcr_public_key": str(base / "pcr-public.pem"),
                  "db_cert": str(base / "db.pem"),
                  "profiles": profiles}
        result, calls = run_tool(base, config)
        require(result.returncode == 0, f"the builder failed: {result.stderr}")
        builds = [c for c in calls if c[:2] == ["ukify", "build"]]
        require(len(builds) == len(profiles) + 1, f"not one build per profile plus the image: {len(builds)}")
        for profile, call in zip(profiles, builds):
            require(f"--profile=TITLE={profile['title']}\nID={profile['id']}" in call
                    and f"--cmdline={profile['cmdline']}" in call, f"profile {profile['id']} built wrongly")
        image = builds[-1]
        require(sum(a.startswith("--join-profile=") for a in image) == len(profiles), "not every profile joined")
        require("--phases=enter-initrd" in image and any(a.startswith("--pcr-private-key=") for a in image)
                and f"--linux={config['kernel']}" in image and f"--initrd={config['initrd']}" in image,
                "the image is not measured with a signed PCR 11 policy")
        signs = [c for c in calls if c[0] in ("sbctl", "sbverify")]
        require(len(signs) == 2 and signs[0][:2] == ["sbctl", "sign"] and signs[0][2].endswith("hyperlab.efi.new")
                and signs[1] == ["sbverify", "--cert", config["db_cert"], signs[0][2]],
                f"the image is not signed and verified against the db key before it replaces the one in use: {signs}")
        linux = esp / "EFI" / "Linux"
        require((linux / "hyperlab.efi").read_text() == "uki" and not (linux / "hyperlab.efi.new").exists(),
                "the verified image did not replace the one in use")
        (linux / "hyperlab.efi").write_text("in use")
        result, _ = run_tool(base, config)
        require(result.returncode == 0 and (linux / "hyperlab-previous.efi").read_text() == "in use",
                "the image in use was not kept as the previous build")
        (linux / "hyperlab.efi").write_text("in use 2")
        result, _ = run_tool(base, config, unsigned=True)
        require(result.returncode == 1 and (linux / "hyperlab.efi").read_text() == "in use 2"
                and not (linux / "hyperlab.efi.new").exists(), "an unverified image replaced the one in use")

        bad = []
        bad.append(dict(config, profiles=[dict(profiles[0], cmdline="quiet rw")]))
        bad.append(dict(config, profiles=[dict(profiles[0], title="two\nlines")]))
        bad.append(dict(config, profiles=[profiles[0], profiles[0]]))
        bad.append(dict(config, profiles=[dict(profiles[0], id="../x")]))
        bad.append(dict(config, profiles=[]))
        (base / "link").symlink_to(base / "vmlinuz")
        bad.append(dict(config, kernel=str(base / "link")))
        for candidate in bad:
            result, calls = run_tool(base, candidate)
            require(result.returncode == 1 and calls == [], f"a malformed configuration was built: {candidate}")


def check_role() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    require(defaults["measured_boot_enabled"] is False, "the UKI ships on before the lab booted it")
    tasks = (ROLE / "tasks/main.yml").read_text()
    require('creates: "{{ measured_boot_key_dir }}/pcr-private.pem"' in tasks, "the PCR signing key could be replaced")
    require('mode: "0600"' in tasks, "the PCR signing key is not private")
    require("Remove the UKI rebuild hook while the UKI is off" in tasks, "the rebuild hook outlives the switch")
    for forbidden in ("loader.conf", "set-default", "bootctl", "cryptenroll", "luksKillSlot", "luksAddKey",
                      "enroll-keys", "efibootmgr"):
        require(forbidden not in tasks, f"the role touches {forbidden}")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    require(bricks["brick_requires"]["measured_boot"] == ["vfio_boot"]
            and bricks["brick_playbooks"]["measured_boot"] == "playbooks/measured-boot.yml",
            "the measured boot brick is not in the graph")


def main() -> int:
    profiles = check_profiles()
    check_builder(profiles)
    check_role()
    print("Measured boot contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
