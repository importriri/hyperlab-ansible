#!/usr/bin/python3
"""hyperlab-spice-dir - libvirt qemu hook. Managed by hyperlab-ansible.

ADR 0037 part 2. With per-Machine QEMU identities a Looking Glass Machine's
SPICE socket lives in its own directory below the SPICE root:

    <root>/<domain>/<domain>.sock

At `prepare` this hook makes that directory, owned by the identity in the
domain's static DAC label, mode 0770, with an ACL for the operator (who runs
the Looking Glass client) and nothing for anyone else, so no other Machine's
QEMU can reach the socket or put a socket in its place. At `release` it
removes the directory. A domain whose socket is not in that form is not
touched. A domain in that form without a static label is refused: libvirt
does not start it.

libvirt passes the domain XML on stdin. The configuration is a root-owned
JSON file: {"root": "/run/hyperlab-spice", "operator": "sid"}.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CONFIG = Path(os.environ.get("HYPERLAB_SPICE_DIR_CONFIG", "/etc/hyperlab/spice-dir.json"))
DRY_RUN = os.environ.get("HYPERLAB_SPICE_DIR_DRY_RUN") == "1"
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
LABEL_RE = re.compile(r"^\+(\d+):\+(\d+)$")


class Refused(RuntimeError):
    pass


def act(*argv: str) -> None:
    if DRY_RUN:
        print("ACTION " + " ".join(argv))
        return
    subprocess.run(argv, check=True)


def socket_path(root: ET.Element) -> str | None:
    for listen in root.findall("./devices/graphics[@type='spice']/listen[@type='socket']"):
        return listen.get("socket")
    return None


def static_label(root: ET.Element) -> tuple[str, str]:
    for seclabel in root.findall("./seclabel"):
        if seclabel.get("model") == "dac" and seclabel.get("type") == "static":
            match = LABEL_RE.fullmatch((seclabel.findtext("./label") or "").strip())
            if match:
                return match.group(1), match.group(2)
    raise Refused("a per-machine SPICE socket needs the domain's static DAC label")


def handle(domain: str, phase: str, xml_text: str, config: dict) -> int:
    if phase not in ("prepare", "release"):
        return 0
    if not DOMAIN_RE.fullmatch(domain):
        return 0
    spice_root = Path(config["root"])
    root = ET.fromstring(xml_text)
    wanted = spice_root / domain / f"{domain}.sock"
    if socket_path(root) != str(wanted):
        return 0
    directory = spice_root / domain
    if phase == "release":
        if directory.is_symlink():
            raise Refused(f"{directory} is a symlink")
        if directory.is_dir():
            if DRY_RUN:
                print(f"ACTION rm -r {directory}")
            else:
                shutil.rmtree(directory)
        return 0
    uid, gid = static_label(root)
    if spice_root.is_symlink() or not spice_root.is_dir():
        raise Refused(f"{spice_root} is not a real directory")
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise Refused(f"{directory} is not a directory this hook made")
    operator = config["operator"]
    pwd.getpwnam(operator)  # refuse an unknown operator before changing anything
    act("install", "-d", "-m", "0770", "-o", uid, "-g", gid, str(directory))
    act("chown", f"{uid}:{gid}", str(directory))
    act("chmod", "0770", str(directory))
    act("setfacl", "--set", f"u::rwx,g::rwx,o::---,u:{operator}:rwx,m::rwx,"
        f"d:u::rwx,d:g::rwx,d:o::---,d:u:{operator}:rwx,d:m::rwx", str(directory))
    return 0


def main(argv: list[str]) -> int:
    domain = argv[1] if len(argv) > 1 else ""
    phase = argv[2] if len(argv) > 2 else ""
    if phase not in ("prepare", "release"):
        return 0
    try:
        config = json.loads(CONFIG.read_text())
        return handle(domain, phase, sys.stdin.read(), config)
    except (Refused, OSError, KeyError, ValueError, ET.ParseError, subprocess.CalledProcessError) as exc:
        print(f"hyperlab-spice-dir: {domain}: {exc}: refusing (fail closed)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
