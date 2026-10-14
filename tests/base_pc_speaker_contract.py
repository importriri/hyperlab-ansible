#!/usr/bin/env python3
"""The host's internal PC speaker stays silent
(problems/host-pc-speaker-beeped.md).

The base role installs a modprobe.d file that blacklists pcspkr and
snd_pcsp, and unloads the loaded ones with rmmod. This contract reads the role, and has modprobe
itself parse the installed file when modprobe is available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/base"
DRIVERS = ("pcspkr", "snd_pcsp")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Base PC speaker contract: {message}")


def main() -> int:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    copies = [task["ansible.builtin.copy"] for task in tasks
              if str(task.get("ansible.builtin.copy", {}).get("dest", "")).startswith("/etc/modprobe.d/")]
    require(len(copies) == 1, "the base role installs no PC speaker blacklist in /etc/modprobe.d")
    copy = copies[0]
    require((copy["owner"], copy["group"], copy["mode"]) == ("root", "root", "0644"),
            f"the blacklist is not root:root 0644: {copy}")
    source = ROLE / "files" / copy["src"]
    lines = [line.split() for line in source.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    require(sorted(lines) == sorted(["blacklist", driver] for driver in DRIVERS),
            f"{source.name} does not blacklist exactly {', '.join(DRIVERS)}: {lines}")

    # modprobe, and the modprobe module, read the running kernel's module
    # tree, which Arch removes on a kernel upgrade until the next boot: the
    # role must not stop there. It reads /sys and unloads with rmmod.
    require(not any("community.general.modprobe" in task or "modprobe" in str(task.get("ansible.builtin.command", ""))
                    for task in tasks),
            "the base role unloads with modprobe, which fails without the running kernel's module tree")
    reads = [task for task in tasks if task.get("ansible.builtin.stat", {}).get("path")
             == "/sys/module/{{ item }}/initstate"]
    require(len(reads) == 1 and sorted(reads[0].get("loop", [])) == sorted(DRIVERS),
            "the base role does not read which PC speaker drivers are loaded from /sys/module")
    register = reads[0].get("register")
    unloads = [task for task in tasks
               if task.get("ansible.builtin.command", {}).get("argv") == ["rmmod", "{{ item.item }}"]]
    require(len(unloads) == 1 and unloads[0].get("loop") == "{{ %s.results }}" % register
            and unloads[0].get("when") == "item.stat.exists",
            "the base role does not rmmod exactly the loaded PC speaker drivers")
    require(unloads[0].get("failed_when") is False,
            "a PC speaker driver in use would stop the base role")

    modprobe = shutil.which("modprobe") or ("/usr/bin/modprobe" if Path("/usr/bin/modprobe").exists() else None)
    if modprobe:
        # -C adds the file to the system's own configuration, so the lines
        # prove something only where the system does not already have them.
        def shown(path: str) -> list[str]:
            return subprocess.run([modprobe, "-C", path, "--showconfig"],
                                  capture_output=True, text=True, check=False).stdout.splitlines()
        baseline = shown(os.devnull)
        if all(f"blacklist {driver}" in baseline for driver in DRIVERS):
            print("Base PC speaker contract: OK (modprobe parse SKIPPED, the system already blacklists both)")
            return 0
        parsed = shown(str(source))
        for driver in DRIVERS:
            require(f"blacklist {driver}" in parsed, f"modprobe does not read 'blacklist {driver}' from {source.name}")
        print("Base PC speaker contract: OK")
    else:
        print("Base PC speaker contract: OK (modprobe parse SKIPPED, no modprobe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
