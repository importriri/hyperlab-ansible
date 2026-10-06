#!/usr/bin/env python3
"""Create, start and remove the nested lab host (ADR 0046) without sudo.

Every libvirt resource this tool touches is named hl-lab-*: the network
hl-lab-testbed, the storage pool hl-lab-pool and its volumes, the domain
hl-lab-host. It runs as the operator's user against qemu:///system, refuses
any other name before calling virsh, and never passes a host device: the
domain definition is checked by tools/lab/hl_lab_check.py before and after
it is defined.

    hl_lab.py check                 nested KVM, free RAM and disk, the ISO
    hl_lab.py create [--iso PATH]   define network, pool, volumes and domain
    hl_lab.py start --isolation-checked
                                    start the network and the domain; only
                                    after the operator has seen the host's
                                    loaded ruleset isolate virbr-hl-lab
    hl_lab.py status                what exists and what runs
    hl_lab.py stop                  ask the lab host to shut down
    hl_lab.py destroy --yes-remove-hl-lab
                                    remove every hl-lab-* resource

The test network's isolation is the host's lab_isolation table, loaded by
playbooks/foundation.yml with privilege. This tool cannot read that table,
so it never claims the network is isolated; `start` requires the operator's
statement that they saw it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hl_lab_check import problems  # noqa: E402

PREFIX = "hl-lab-"
CONNECT = "qemu:///system"
DOMAIN = "hl-lab-host"
NETWORK = "hl-lab-testbed"
POOL = "hl-lab-pool"
POOL_DIR = "/var/lib/libvirt/images/hl-lab"
DISK = "hl-lab-host.qcow2"
ISO_VOLUME = "hl-lab-install.iso"
SEED_VOLUME = "hl-lab-seed.iso"
MEMORY_MIB = 4096
VCPUS = 4
DISK_GIB = 80
# Left to the host after the lab host takes its memory and disk.
HOST_MEMORY_MARGIN_MIB = 3072
HOST_DISK_MARGIN_GIB = 100
STATE = Path.home() / ".local/share/hyperlab-lab"
KEY = STATE / "id_ed25519"
TEMPLATE = Path(__file__).resolve().parent / "hl-lab-host.xml"
ISOLATION_CHECK = (
    "sudo nft list chain inet lab_isolation input | grep -E 'virbr-hl-lab|\"virbr\\*\"'"
)

# virsh verbs that change something. Every argument naming a libvirt object
# for these must carry the prefix.
MUTATING = {
    "net-define", "net-start", "net-autostart", "net-destroy", "net-undefine",
    "pool-define-as", "pool-build", "pool-start", "pool-autostart", "pool-destroy",
    "pool-undefine", "pool-delete", "vol-create-as", "vol-upload", "vol-delete",
    "define", "start", "shutdown", "destroy", "undefine",
}


class Refused(RuntimeError):
    pass


def lab_name(name: str) -> str:
    if not name.startswith(PREFIX) or "/" in name or len(name) > 64:
        raise Refused(f"{name!r} is not a lab resource; only {PREFIX}* names are touched")
    return name


def virsh(*args: str, check: bool = True, run=subprocess.run) -> subprocess.CompletedProcess:
    verb = args[0]
    if verb in MUTATING:
        # The object the verb acts on is its first positional argument.
        positional = [a for a in args[1:] if not a.startswith("-")]
        if verb in ("net-define", "define"):
            pass  # a file; the name inside it is checked before
        elif verb == "vol-create-as":
            lab_name(positional[0])
            lab_name(positional[1])
        elif verb in ("vol-upload", "vol-delete"):
            lab_name(positional[0])
            pool = args[args.index("--pool") + 1]
            lab_name(pool)
        else:
            lab_name(positional[0])
    result = run(["virsh", "--connect", CONNECT, *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise Refused(f"virsh {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result


def names(kind: str) -> set[str]:
    listing = {"net": ["net-list", "--all", "--name"], "pool": ["pool-list", "--all", "--name"],
               "dom": ["list", "--all", "--name"]}[kind]
    return {line.strip() for line in virsh(*listing).stdout.splitlines() if line.strip()}


def lab_network() -> dict:
    networks = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())["lab_host_networks"]
    match = [n for n in networks if n["name"] == NETWORK]
    if len(match) != 1:
        raise Refused(f"{NETWORK} is not declared in group_vars/all/networks.yml")
    return match[0]


def network_xml(net: dict) -> str:
    base = net["subnet"].rsplit(".", 1)[0]
    return (f"<network>\n  <name>{net['name']}</name>\n"
            f"  <bridge name=\"{net['bridge']}\" stp=\"on\" delay=\"0\"/>\n"
            "  <forward mode=\"nat\"/>\n"
            f"  <ip address=\"{net['gateway']}\" netmask=\"255.255.255.0\">\n"
            f"    <dhcp>\n      <range start=\"{base}.100\" end=\"{base}.199\"/>\n    </dhcp>\n"
            "  </ip>\n</network>\n")


def domain_xml(with_iso: bool) -> str:
    text = TEMPLATE.read_text()
    install = ""
    if with_iso:
        install = (
            "    <disk type=\"volume\" device=\"cdrom\">\n"
            f"      <source pool=\"{POOL}\" volume=\"{ISO_VOLUME}\"/>\n"
            "      <target dev=\"sda\" bus=\"sata\"/>\n      <readonly/>\n      <boot order=\"2\"/>\n"
            "    </disk>\n"
            "    <disk type=\"volume\" device=\"cdrom\">\n"
            f"      <source pool=\"{POOL}\" volume=\"{SEED_VOLUME}\"/>\n"
            "      <target dev=\"sdb\" bus=\"sata\"/>\n      <readonly/>\n"
            "    </disk>\n")
    return (text.replace("@@NAME@@", DOMAIN).replace("@@MEMORY@@", str(MEMORY_MIB))
            .replace("@@VCPUS@@", str(VCPUS)).replace("@@POOL@@", POOL).replace("@@DISK@@", DISK)
            .replace("@@NETWORK@@", NETWORK).replace("@@INSTALL@@\n", install))


def check_host(iso: Path | None) -> list[str]:
    found = []
    nested = Path("/sys/module/kvm_intel/parameters/nested")
    if not nested.exists() or nested.read_text().strip() not in ("Y", "1"):
        found.append("nested KVM is off")
    meminfo = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(meminfo["MemAvailable"].split()[0]) // 1024
    if available < MEMORY_MIB + HOST_MEMORY_MARGIN_MIB:
        found.append(f"{available} MiB free; the lab host needs {MEMORY_MIB} MiB and the host keeps "
                     f"{HOST_MEMORY_MARGIN_MIB} MiB")
    free = shutil.disk_usage("/var/lib/libvirt/images").free // (1 << 30)
    if free < DISK_GIB + HOST_DISK_MARGIN_GIB:
        found.append(f"{free} GiB free on the image store; the lab host needs {DISK_GIB} GiB and the "
                     f"host keeps {HOST_DISK_MARGIN_GIB} GiB")
    if iso is not None and not iso.is_file():
        found.append(f"no ISO at {iso}")
    return found


def ensure_key() -> str:
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not KEY.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "hyperlab-lab-agent",
                        "-f", str(KEY)], check=True)
    return (KEY.with_suffix(".pub")).read_text().strip()


def seed_image(public_key: str, directory: Path) -> Path:
    user_data = directory / "user-data"
    user_data.write_text(
        "#cloud-config\n"
        "runcmd:\n"
        "  - [install, -d, -m, '0700', /root/.ssh]\n"
        f"  - [sh, -c, \"printf '%s\\\\n' '{public_key}' > /root/.ssh/authorized_keys\"]\n"
        "  - [chmod, '0600', /root/.ssh/authorized_keys]\n"
        "  - [systemctl, start, sshd.service]\n")
    (directory / "meta-data").write_text(f"instance-id: {DOMAIN}\nlocal-hostname: {DOMAIN}\n")
    seed = directory / SEED_VOLUME
    subprocess.run(["cloud-localds", str(seed), str(user_data), str(directory / "meta-data")], check=True)
    return seed


def upload(path: Path, volume: str, fmt: str = "raw") -> None:
    size = path.stat().st_size
    virsh("vol-create-as", POOL, volume, str(size), "--format", fmt)
    virsh("vol-upload", volume, str(path), "--pool", POOL)


def checked(xml: str, what: str) -> None:
    import xml.etree.ElementTree as ET
    found = problems(ET.fromstring(xml))
    if found:
        raise Refused(f"{what} refused: " + "; ".join(found))


def create(iso: Path | None) -> None:
    found = check_host(iso)
    if found:
        raise Refused("; ".join(found))
    net = lab_network()
    public_key = ensure_key()
    with tempfile.TemporaryDirectory(prefix="hl-lab-") as temp:
        directory = Path(temp)
        if NETWORK not in names("net"):
            path = directory / "net.xml"
            path.write_text(network_xml(net))
            virsh("net-define", str(path))
        if POOL not in names("pool"):
            virsh("pool-define-as", POOL, "dir", "--target", POOL_DIR)
            virsh("pool-build", POOL)
            virsh("pool-start", POOL)
            virsh("pool-autostart", POOL)
        volumes = set(virsh("vol-list", POOL, "--name").stdout.split())
        if DISK not in volumes:
            virsh("vol-create-as", POOL, DISK, f"{DISK_GIB}G", "--format", "qcow2")
        if iso is not None and ISO_VOLUME not in volumes:
            upload(iso, ISO_VOLUME)
        if iso is not None and SEED_VOLUME not in volumes:
            upload(seed_image(public_key, directory), SEED_VOLUME)
        if DOMAIN not in names("dom"):
            xml = domain_xml(with_iso=iso is not None)
            checked(xml, "the lab host definition")
            path = directory / "domain.xml"
            path.write_text(xml)
            virsh("define", str(path))
    checked(virsh("dumpxml", "--inactive", DOMAIN).stdout, "the defined lab host")
    print(f"defined {NETWORK}, {POOL} and {DOMAIN}; nothing is started")


def start(isolation_checked: bool) -> None:
    if not isolation_checked:
        raise Refused("the host's isolation of virbr-hl-lab is not confirmed. Run, as the operator:\n  "
                      + ISOLATION_CHECK + "\nand pass --isolation-checked only if both the bridge's "
                      "rules and the virbr* catch-all are listed")
    checked(virsh("dumpxml", "--inactive", DOMAIN).stdout, "the defined lab host")
    if "Active:         yes" not in virsh("net-info", NETWORK).stdout:
        virsh("net-start", NETWORK)
    if DOMAIN not in {line.strip() for line in virsh("list", "--name").stdout.splitlines()}:
        virsh("start", DOMAIN)
    print(f"{DOMAIN} started on {NETWORK}")


def status() -> None:
    for kind, name in (("net", NETWORK), ("pool", POOL), ("dom", DOMAIN)):
        print(f"{name}: {'defined' if name in names(kind) else 'absent'}")
    if DOMAIN in names("dom"):
        print(virsh("domstate", DOMAIN).stdout.strip())


def stop() -> None:
    virsh("shutdown", DOMAIN)


def destroy() -> None:
    running = {line.strip() for line in virsh("list", "--name").stdout.splitlines()}
    if DOMAIN in names("dom"):
        if DOMAIN in running:
            virsh("destroy", DOMAIN)
        virsh("undefine", DOMAIN, "--nvram", "--tpm")
    if POOL in names("pool"):
        for volume in virsh("vol-list", POOL, "--name").stdout.split():
            virsh("vol-delete", lab_name(volume), "--pool", POOL)
        virsh("pool-destroy", POOL, check=False)
        virsh("pool-delete", POOL, check=False)
        virsh("pool-undefine", POOL)
    if NETWORK in names("net"):
        virsh("net-destroy", NETWORK, check=False)
        virsh("net-undefine", NETWORK)
    print("every hl-lab-* resource is removed")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").add_argument("--iso", type=Path)
    sub.add_parser("create").add_argument("--iso", type=Path)
    sub.add_parser("start").add_argument("--isolation-checked", action="store_true")
    sub.add_parser("status")
    sub.add_parser("stop")
    sub.add_parser("destroy").add_argument("--yes-remove-hl-lab", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            found = check_host(args.iso)
            for line in found:
                print("FAIL", line)
            print("OK" if not found else "")
            return 1 if found else 0
        if args.command == "create":
            create(args.iso)
        elif args.command == "start":
            start(args.isolation_checked)
        elif args.command == "status":
            status()
        elif args.command == "stop":
            stop()
        elif args.command == "destroy":
            if not args.yes_remove_hl_lab:
                raise Refused("destroy removes every hl-lab-* resource; pass --yes-remove-hl-lab")
            destroy()
    except Refused as exc:
        print(f"hl-lab: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main(sys.argv[1:]))
