#!/usr/bin/env python3
"""vfio_boot asks for the file mode the ESP keeps
(problems/vfio-boot-modes-on-vfat-esp.md).

arch-bootstrap mounts the ESP on /boot as vfat. A vfat file's mode comes
from the mount (fmask, showexec), and chmod cannot change it, so a fixed
0644 on the boot entries and loader.conf was a change on every run of the
Nitro, whose ESP gives 0755. The role now reads the mount of every /boot
directory it writes into with findmnt, and tools/esp_file_mode.py decides
the mode: the one vfat gives, or the role's 0644 on a filesystem that keeps
modes. Anything it cannot decide, or a mount that lets anyone but root
write a boot entry, is a refusal.

This contract runs the tool on findmnt documents (the first is the Nitro's
real one) and reads the role's tasks.
"""
from __future__ import annotations

import json
import posixpath
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/vfio_boot"
TOOL = ROOT / "tools/esp_file_mode.py"
NITRO_OPTIONS = ("rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=ascii,"
                 "shortname=mixed,utf8,errors=remount-ro")
MODE_FACT = "{{ vfio_boot_loader_file_mode }}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"vfio_boot ESP mode contract: {message}")


def findmnt(fstype: str, options: str, target: str = "/boot") -> str:
    return json.dumps({"filesystems": [{"target": target, "fstype": fstype, "options": options}]},
                      indent=3)


def run_tool(stdin: str, wanted: str = "0644") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), "--wanted", wanted], input=stdin,
                          capture_output=True, text=True, check=False)


def decided(documents: list[str], wanted: str = "0644") -> str:
    result = run_tool(json.dumps(documents), wanted)
    require(result.returncode == 0, f"the tool refused a mount it must decide: {result.stderr.strip()}")
    return result.stdout.strip()


def refused(stdin: str, reason: str, wanted: str = "0644") -> None:
    result = run_tool(stdin, wanted)
    require(result.returncode != 0 and result.stdout == "" and result.stderr.strip(),
            f"the tool accepted {reason}: rc={result.returncode} stdout={result.stdout!r}")


def check_tool() -> None:
    nitro = findmnt("vfat", NITRO_OPTIONS)
    require(decided([nitro, nitro]) == "0755",
            "the mode decided for the Nitro's ESP (fmask=0022) is not the 0755 its files read")
    require(decided([findmnt("vfat", "rw,fmask=0133,dmask=0022")]) == "0644",
            "fmask=0133 does not give 0644")
    require(decided([findmnt("vfat", "rw,fmask=0077,dmask=0077")]) == "0700",
            "fmask=0077 does not give 0700")
    require(decided([findmnt("vfat", "rw,fmask=0022,dmask=0022,showexec")]) == "0644",
            "showexec does not take the execute bits from a .conf file")
    for fstype in ("ext4", "btrfs", "xfs"):
        require(decided([findmnt(fstype, "rw,relatime")]) == "0644",
                f"{fstype} keeps modes but the role's 0644 was not kept")
    require(decided([findmnt("ext4", "rw")], wanted="0600") == "0600",
            "the wanted mode is not the one asked for on a filesystem that keeps modes")

    refused(json.dumps([findmnt("vfat", "rw,fmask=0000,dmask=0000")]),
            "fmask=0000, which lets everyone write a boot entry")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0002,dmask=0022")]), "fmask=0002 (others write)")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0020,dmask=0022")]), "fmask=0020 (group writes)")
    refused(json.dumps([findmnt("vfat", "rw,relatime,dmask=0022")]), "a vfat mount without fmask")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,fmask=0133")]), "a duplicated fmask")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0x22")]), "a fmask that is not octal")
    refused(json.dumps([findmnt("vfat", "rw,fmask=01022")]), "a fmask beyond the permission bits")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,uid=1000")]),
            "a vfat mount whose files belong to uid 1000, not root")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,gid=100")]),
            "a vfat mount whose files belong to gid 100, not root")
    for fstype in ("exfat", "ntfs3", "msdos", "nfs4", ""):
        refused(json.dumps([findmnt(fstype, "rw,fmask=0022")]), f"fstype {fstype!r}")
    refused(json.dumps([nitro, findmnt("vfat", NITRO_OPTIONS, target="/boot/loader")]),
            "two directories on different filesystems")
    refused(json.dumps([nitro, findmnt("vfat", "rw,fmask=0133,dmask=0022")]),
            "two documents with different options")
    refused(json.dumps([]), "no document")
    refused(json.dumps(nitro), "a document that is not in a list")
    refused("not json", "stdin that is not JSON")
    refused(json.dumps(["not json"]), "a document that is not JSON")
    refused(json.dumps([json.dumps({"filesystems": []})]), "a document without a filesystem")
    two = {"filesystems": [json.loads(nitro)["filesystems"][0]] * 2}
    refused(json.dumps([json.dumps(two)]), "a document with two filesystems")
    refused(json.dumps([findmnt("vfat", NITRO_OPTIONS, target="boot")]), "a relative target")
    for wanted in ("644", "0664", "0646", "0x1a4", "07777"):
        refused(json.dumps([findmnt("ext4", "rw")]), f"--wanted {wanted}", wanted=wanted)


def module_args(task: dict[str, Any]) -> dict[str, Any]:
    for key, value in task.items():
        if key.startswith("ansible.builtin.") and isinstance(value, dict):
            return value
    return {}


def check_role() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text(encoding="utf-8"))
    require(defaults.get("vfio_boot_file_mode") == "0644",
            "the mode wanted where the filesystem keeps modes is not 0644")
    require(defaults.get("vfio_boot_findmnt_bin") == "/usr/bin/findmnt",
            "vfio_boot does not name findmnt by its absolute path")
    require(defaults.get("vfio_boot_python_bin") == "/usr/bin/python",
            "vfio_boot does not name python by its absolute path")
    require(defaults.get("vfio_boot_mode_tool")
            == "{{ (vfio_boot_repository_root, 'tools/esp_file_mode.py') | path_join }}"
            and defaults.get("vfio_boot_repository_root") == "{{ playbook_dir | dirname }}",
            "vfio_boot does not run this repository's tools/esp_file_mode.py")

    writers: list[tuple[int, str]] = []
    for index, task in enumerate(tasks):
        args = module_args(task)
        target = str(args.get("dest", args.get("path", "")))
        if target.startswith("/boot/") and "mode" in args:
            require(args["mode"] == MODE_FACT,
                    f"'{task['name']}' writes {target} with a fixed mode {args['mode']!r}, "
                    "not the one the ESP keeps")
            writers.append((index, target))
    require(len(writers) >= 2, "vfio_boot no longer writes the boot entries and loader.conf with the decided mode")
    directories = sorted({posixpath.dirname(target) for _, target in writers})

    names = [task["name"] for task in tasks]
    read = [i for i, task in enumerate(tasks)
            if module_args(task).get("argv", [None])[0] == "{{ vfio_boot_findmnt_bin }}"]
    require(len(read) == 1, "vfio_boot does not read the ESP's mount with findmnt exactly once")
    read_task = tasks[read[0]]
    require(module_args(read_task)["argv"] == ["{{ vfio_boot_findmnt_bin }}", "-J", "-T", "{{ item }}",
                                               "-o", "TARGET,FSTYPE,OPTIONS"],
            f"findmnt is not asked for one target's TARGET,FSTYPE,OPTIONS: {module_args(read_task)['argv']}")
    looped = sorted(read_task.get("loop", []))
    for directory in directories:
        require(directory in looped, f"vfio_boot does not inspect {directory}, where it writes")
    require(looped == directories, f"findmnt inspects {looped}, not exactly {directories}")

    decide = [i for i, task in enumerate(tasks)
              if module_args(task).get("argv", [None, None])[1:2] == ["{{ vfio_boot_mode_tool }}"]]
    require(len(decide) == 1, "vfio_boot does not run tools/esp_file_mode.py exactly once")
    decide_task = tasks[decide[0]]
    require(module_args(decide_task)["argv"] == ["{{ vfio_boot_python_bin }}", "{{ vfio_boot_mode_tool }}",
                                                 "--wanted", "{{ vfio_boot_file_mode }}"],
            f"the tool is not asked for the role's wanted mode: {module_args(decide_task)['argv']}")
    require(module_args(decide_task).get("stdin")
            == "{{ %s.results | map(attribute='stdout') | list | to_json }}" % read_task["register"],
            "the tool does not read every findmnt document the role collected")
    for task in (read_task, decide_task):
        require(task.get("check_mode") is False,
                f"'{task['name']}' only reads, but does not run in check mode, so --check --diff "
                "cannot compare the mode")
        require(task.get("changed_when") is False, f"'{task['name']}' only reads but may report a change")

    publish = [i for i, task in enumerate(tasks)
               if "vfio_boot_loader_file_mode" in task.get("ansible.builtin.set_fact", {})]
    require(len(publish) == 1 and tasks[publish[0]]["ansible.builtin.set_fact"]["vfio_boot_loader_file_mode"]
            == "{{ %s.stdout }}" % decide_task["register"],
            "vfio_boot_loader_file_mode is not the tool's answer")
    first_write = min(index for index, _ in writers)
    require(read[0] < decide[0] < publish[0] < first_write,
            "the mode is decided after '%s' writes under /boot" % names[first_write])


def main() -> int:
    check_tool()
    check_role()
    print("vfio_boot ESP mode contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
