#!/usr/bin/python3
"""hyperlab-uki-build - one signed, measured, multi-profile UKI (ADR 0044).

Builds EFI/Linux/hyperlab.efi from the running kernel and initramfs with one
profile per boot entry (the same command line as the type 1 entry it
mirrors), with signed PCR 11 policies for the enter-initrd phase, signs it
with the host's sbctl keys and checks the signature before it replaces the
UKI in use. The UKI it replaces is kept as hyperlab-previous.efi, so the
boot menu still offers the previous build if the new one fails. Type 1
entries and the default entry are never touched here.

Configuration: /etc/hyperlab/uki.json
  {"kernel": "/boot/vmlinuz-linux-hardened",
   "initrd": "/boot/initramfs-linux-hardened.img",
   "esp": "/boot",
   "pcr_private_key": "/etc/hyperlab/uki/pcr-private.pem",
   "pcr_public_key": "/etc/hyperlab/uki/pcr-public.pem",
   "db_cert": "/var/lib/sbctl/keys/db/db.pem",
   "profiles": [{"id": "vfio", "title": "Arch Linux (Vfio)", "cmdline": "..."}, ...]}
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CONFIG = Path(os.environ.get("HYPERLAB_UKI_CONFIG", "/etc/hyperlab/uki.json"))
UKIFY = os.environ.get("HYPERLAB_UKIFY", "/usr/bin/ukify")
SBCTL = os.environ.get("HYPERLAB_SBCTL", "/usr/bin/sbctl")
SBVERIFY = os.environ.get("HYPERLAB_SBVERIFY", "/usr/bin/sbverify")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
NAME = "hyperlab.efi"
PREVIOUS = "hyperlab-previous.efi"


class Refused(RuntimeError):
    pass


def run(*argv: str) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise Refused(f"{Path(argv[0]).name} {argv[1] if len(argv) > 1 else ''} failed: "
                      f"{(result.stderr or result.stdout).strip()[-400:]}")
    return result


def load() -> dict:
    config = json.loads(CONFIG.read_text())
    profiles = config.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise Refused("the configuration names no profile")
    seen = set()
    for profile in profiles:
        if not isinstance(profile, dict) or not ID_RE.fullmatch(str(profile.get("id", ""))):
            raise Refused(f"invalid profile id in {profile!r}")
        if profile["id"] in seen:
            raise Refused(f"profile {profile['id']} appears twice")
        seen.add(profile["id"])
        for key in ("title", "cmdline"):
            value = profile.get(key)
            if not isinstance(value, str) or not value or "\n" in value:
                raise Refused(f"profile {profile['id']} has no single-line {key}")
        if "root=" not in profile["cmdline"]:
            raise Refused(f"profile {profile['id']}'s command line has no root=")
    for key in ("kernel", "initrd", "pcr_private_key", "pcr_public_key", "db_cert"):
        path = Path(str(config.get(key, "")))
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise Refused(f"{key} is not a regular file: {path}")
    esp = Path(str(config.get("esp", "")))
    if not esp.is_absolute() or not esp.is_dir():
        raise Refused(f"the ESP {esp} is not a directory")
    return config


def build(config: dict, workdir: Path) -> Path:
    joined = []
    for index, profile in enumerate(config["profiles"]):
        output = workdir / f"profile{index}.efi"
        run(UKIFY, "build", f"--profile=TITLE={profile['title']}\nID={profile['id']}",
            f"--cmdline={profile['cmdline']}", f"--output={output}")
        joined.append(f"--join-profile={output}")
    uki = workdir / NAME
    run(UKIFY, "build", f"--linux={config['kernel']}", f"--initrd={config['initrd']}",
        f"--pcr-private-key={config['pcr_private_key']}",
        f"--pcr-public-key={config['pcr_public_key']}",
        "--phases=enter-initrd", *joined, f"--output={uki}")
    return uki


def install(config: dict, uki: Path) -> Path:
    target_dir = Path(config["esp"]) / "EFI" / "Linux"
    target_dir.mkdir(parents=True, exist_ok=True)
    staged = target_dir / (NAME + ".new")
    shutil.copyfile(uki, staged)
    # sbctl signs with the host's db key; sbverify checks this one file
    # against that key's certificate, which sbctl's own verify cannot do.
    run(SBCTL, "sign", str(staged))
    verified = subprocess.run([SBVERIFY, "--cert", config["db_cert"], str(staged)],
                              capture_output=True, text=True, check=False)
    if verified.returncode != 0:
        staged.unlink(missing_ok=True)
        raise Refused(f"{staged} does not verify against the db key: "
                      f"{(verified.stderr or verified.stdout).strip()[-200:]}")
    current = target_dir / NAME
    if current.exists():
        os.replace(current, target_dir / PREVIOUS)
    os.replace(staged, current)
    return current


def main(argv: list[str]) -> int:
    try:
        config = load()
        with tempfile.TemporaryDirectory(prefix="hyperlab-uki-") as temp:
            current = install(config, build(config, Path(temp)))
        print(f"hyperlab-uki-build: {current} built with {len(config['profiles'])} profiles, signed")
        return 0
    except (Refused, OSError, ValueError, KeyError) as exc:
        print(f"hyperlab-uki-build: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
