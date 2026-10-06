#!/usr/bin/env python3
"""One AppArmor profile confines every QEMU process (ADR 0037, option A2).

  1. the profile attaches to the QEMU binary, gives QEMU no capability, and
     names the host's own data (homes, root, shadow, sudoers, SSH, the
     store's state and TPM directories) in audited deny rules;
  2. evaluated as AppArmor would (deny wins, `*` within a path segment, `**`
     across), the files a Machine uses are granted as they must be (disks,
     transient overlays and NVRAM read and written, seeds and sealed bases
     only read, the lab host's volumes) and the host's data is not;
  3. the role refuses a mode other than complain or enforce, starts in
     complain, validates the profile with apparmor_parser before installing
     it, loads it only on a kernel running AppArmor, and then checks it is
     loaded in the reviewed mode;
  4. when an AppArmor parser is available (HYPERLAB_APPARMOR_PARSER, or
     apparmor_parser on PATH) both modes compile.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/qemu_apparmor"
STORE = yaml.safe_load((ROOT / "group_vars/all/storage.yml").read_text())["hyperlab_root"]
SPICE = yaml.safe_load((ROOT / "group_vars/all/looking-glass.yml").read_text())[
    "hyperlab_looking_glass_spice_socket_dir"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def render(mode: str) -> str:
    variables = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    variables.update(qemu_apparmor_mode=mode, hyperlab_root=STORE,
                     hyperlab_looking_glass_spice_socket_dir=SPICE)
    return jinja2.Template((ROLE / "templates/hyperlab-qemu.j2").read_text(),
                           undefined=jinja2.StrictUndefined).render(**variables)


def glob_regex(pattern: str) -> re.Pattern:
    pattern = pattern.replace("@{HOME}", "/home/*").replace("@{PROC}", "/proc").replace("@{sys}", "/sys")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "{":
            j = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(part) for part in pattern[i + 1:j].split(",")) + ")"
            i = j + 1
        elif pattern[i] == "[":
            j = pattern.index("]", i)
            out += pattern[i:j + 1]
            i = j + 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def file_rules(profile: str) -> list[tuple[bool, re.Pattern, set[str]]]:
    rules = []
    for line in profile.splitlines():
        line = line.strip().rstrip(",")
        match = re.fullmatch(r"(audit\s+)?(deny\s+)?(owner\s+)?(/\S+|@\{\w+\}\S*)\s+([rwklmix]+)", line)
        if match:
            rules.append((bool(match.group(2)), glob_regex(match.group(4)), set(match.group(5))))
    return rules


def allowed(rules, path: str, access: str) -> bool:
    granted = set()
    for deny, regex, modes in rules:
        if regex.match(path):
            if deny and set(access) & modes:
                return False
            if not deny:
                granted |= modes
    return set(access) <= granted


def main() -> int:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    require(defaults["qemu_apparmor_mode"] == "complain", "the QEMU profile starts in enforce before any test")
    for mode in ("complain", "enforce"):
        profile = render(mode)
        require(f"profile hyperlab-qemu /usr/bin/qemu-system-x86_64 flags=({mode})" in profile,
                "the profile does not attach to the QEMU binary in the chosen mode")
        allow_caps = [line for line in profile.splitlines()
                      if re.match(r"\s*capability\b", line)]
        require(allow_caps == [], f"the profile gives QEMU a capability: {allow_caps}")
        require("audit deny capability," in profile, "capabilities are not denied")

    rules = file_rules(render("enforce"))
    for path, access in (
        (f"{STORE}/permanent/dev-01.qcow2", "rwk"),
        (f"{STORE}/disposable/srv-fed-01.qcow2", "rw"),
        (f"{STORE}/disposable/srv-fed-01.qcow2.TRANSIENT-vda", "rw"),
        (f"{STORE}/nvram/dev-01_VARS.fd", "rw"),
        (f"{STORE}/cloud-init/dev-01/seed.iso", "r"),
        (f"{STORE}/bases/linux/arch-20261003.qcow2", "r"),
        ("/var/lib/libvirt/images/hl-lab/hl-lab-host.qcow2", "rw"),
        ("/var/lib/libvirt/qemu/nvram/hl-lab-host_VARS.fd", "rw"),
        ("/var/lib/libvirt/qemu/domain-3-dev-01/monitor.sock", "rw"),
        ("/var/log/libvirt/qemu/dev-01.log", "w"),
        (f"{SPICE}/dev-01.sock", "rw"),
        ("/dev/kvm", "rw"),
        ("/dev/kvmfr0", "rw"),
        ("/dev/vfio/12", "rw"),
        ("/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd", "r"),
    ):
        require(allowed(rules, path, access), f"a Machine's QEMU is refused {access} on {path}")
    for path, access in (
        (f"{STORE}/bases/linux/arch-20261003.qcow2", "w"),
        (f"{STORE}/cloud-init/dev-01/seed.iso", "w"),
        (f"{STORE}/state/vms/dev-01.yml", "r"),
        (f"{STORE}/tpm/dev-01/tpm2-00.permall", "r"),
        ("/home/sid/.ssh/id_ed25519", "r"),
        ("/home/sid/notes.txt", "r"),
        ("/root/.bashrc", "r"),
        ("/etc/shadow", "r"),
        ("/etc/sudoers.d/90-wheel", "r"),
        ("/etc/ssh/ssh_host_ed25519_key", "r"),
        ("/boot/vmlinuz-linux-hardened", "w"),
        ("/etc/libvirt/qemu.conf", "w"),
        ("/etc/gpu-handoff/domains.d/dev-01.conf", "w"),
        ("/var/lib/libvirt/images/other.qcow2", "r"),
        ("/dev/sda", "r"),
    ):
        require(not allowed(rules, path, access), f"QEMU may {access} {path}")

    tasks = (ROLE / "tasks/main.yml").read_text()
    require("qemu_apparmor_mode in ['complain', 'enforce']" in tasks, "the role accepts any mode")
    require("validate: apparmor_parser --skip-kernel-load" in tasks,
            "a profile the parser refuses could replace the loaded one")
    require("path: /sys/kernel/security/apparmor/profiles" in tasks
            and "when: qemu_apparmor_kernel.stat.exists" in tasks,
            "the role does not tell an AppArmor kernel from another")
    require("Require the QEMU profile loaded in the reviewed mode" in tasks,
            "the loaded mode is not checked")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    require(bricks["brick_requires"]["qemu_apparmor"] == ["kvm_host"]
            and bricks["brick_playbooks"]["qemu_apparmor"] == "playbooks/qemu-apparmor.yml",
            "the QEMU profile brick is not in the graph")

    parser = os.environ.get("HYPERLAB_APPARMOR_PARSER") or shutil.which("apparmor_parser")
    if parser:
        base = os.environ.get("HYPERLAB_APPARMOR_BASE", "/etc/apparmor.d")
        env = dict(os.environ)
        if os.environ.get("HYPERLAB_APPARMOR_LIBS"):
            env["LD_LIBRARY_PATH"] = os.environ["HYPERLAB_APPARMOR_LIBS"]
        for mode in ("complain", "enforce"):
            with tempfile.NamedTemporaryFile("w", suffix=".profile") as handle:
                handle.write(render(mode))
                handle.flush()
                result = subprocess.run([parser, "-Q", "-K", "-b", base, "-I", base, "-o", os.devnull, handle.name],
                                        capture_output=True, text=True, env=env, check=False)
                require(result.returncode == 0, f"apparmor_parser refused the {mode} profile: {result.stderr}")
        print("QEMU AppArmor profile contract: OK (compiled)")
    else:
        print("QEMU AppArmor profile contract: OK (no apparmor_parser here; not compiled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
