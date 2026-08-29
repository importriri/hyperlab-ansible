#!/usr/bin/env python3
"""Read-only in-guest gate for NVIDIA, IVSHMEM and the Linux sender build."""
from __future__ import annotations

import argparse
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


class GateError(ValueError):
    """The accelerated guest is not ready for the interactive sender gate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def command(*argv: str) -> str:
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    require(result.returncode == 0, result.stderr.strip() or "command failed")
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[2]),
    )
    parser.add_argument(
        "--stamp",
        default="/usr/local/share/looking-glass-linux-host/built-from.yml",
    )
    parser.add_argument(
        "--sender",
        default="/usr/local/bin/looking-glass-host",
    )
    parser.add_argument(
        "--config",
        default=str(Path.home() / "looking-glass-host.ini"),
    )
    parser.add_argument(
        "--portal-config",
        default=None,
    )
    return parser.parse_args()


def load_expected_pin(repo_root: Path) -> tuple[str, str]:
    path = repo_root / "group_vars/all/looking-glass.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "Looking Glass variables must be a mapping")
    commit = data.get("hyperlab_looking_glass_commit")
    build = data.get("hyperlab_looking_glass_build")
    require(isinstance(commit, str) and len(commit) == 40, "invalid Looking Glass commit pin")
    require(isinstance(build, str) and build, "invalid Looking Glass build pin")
    return commit, build


def load_expected_transport(
    repo_root: Path,
) -> tuple[str, str, str]:
    path = (
        repo_root
        / "roles/guest_looking_glass_linux/defaults/main.yml"
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "guest transport defaults must be a mapping")
    device = data.get("guest_looking_glass_linux_kvmfr_device")
    version = data.get("guest_looking_glass_linux_kvmfr_version")
    patch_sha256 = data.get(
        "guest_looking_glass_linux_compat_patch_sha256"
    )
    require(isinstance(device, str) and device, "invalid guest kvmfr device")
    require(isinstance(version, str) and version, "invalid guest kvmfr version")
    require(
        isinstance(patch_sha256, str)
        and len(patch_sha256) == 64,
        "invalid sender compatibility patch hash",
    )
    return device, version, patch_sha256


def load_expected_portal(repo_root: Path) -> tuple[str, int, str]:
    path = (
        repo_root
        / "roles/guest_looking_glass_linux/defaults/main.yml"
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "guest portal defaults must be a mapping")
    output = data.get("guest_looking_glass_linux_capture_output")
    max_fps = data.get("guest_looking_glass_linux_capture_max_fps")
    picker = data.get("guest_looking_glass_linux_xdph_picker")
    require(isinstance(output, str) and output, "invalid XDPH capture output")
    require(
        isinstance(max_fps, int)
        and not isinstance(max_fps, bool)
        and 0 < max_fps <= 240,
        "invalid XDPH capture frame limit",
    )
    require(
        isinstance(picker, str) and picker.startswith("/usr/local/bin/"),
        "invalid XDPH picker path",
    )
    return output, max_fps, picker


def load_sender_config(
    path: Path,
    expected_kvmfr_device: str,
) -> tuple[str, int]:
    config_stat = path.lstat()
    require(
        stat.S_ISREG(config_stat.st_mode),
        "user sender configuration is not a regular file",
    )
    config_text = path.read_text(encoding="utf-8")
    require("capture=pipewire" in config_text, "PipeWire capture is not selected")
    require(
        f"shmFile={expected_kvmfr_device}" in config_text,
        "sender is not bound to the reviewed guest kvmfr device",
    )
    return config_text, config_stat.st_uid


def require_transport_owner(device_uid: int, sender_uid: int) -> None:
    require(
        device_uid == sender_uid,
        "guest kvmfr transport is not owned by the sender configuration user",
    )


def load_portal_config(
    path: Path,
    expected_picker: str,
    expected_max_fps: int,
    expected_owner_uid: int,
) -> str:
    config_stat = path.lstat()
    require(
        stat.S_ISREG(config_stat.st_mode),
        "XDPH configuration is not a regular file",
    )
    require(
        stat.S_IMODE(config_stat.st_mode) == 0o600,
        "XDPH configuration mode drift",
    )
    require(
        config_stat.st_uid == expected_owner_uid,
        "XDPH configuration is not owned by the sender user",
    )
    config_text = path.read_text(encoding="utf-8")
    require(
        f"max_fps = {expected_max_fps}" in config_text,
        "XDPH capture frame limit drift",
    )
    require(
        f"custom_picker_binary = {expected_picker}" in config_text,
        "XDPH deterministic picker drift",
    )
    return config_text


def load_capture_picker(
    path: Path,
    expected_output: str,
    expected_owner_uid: int = 0,
) -> str:
    picker_stat = path.lstat()
    require(
        stat.S_ISREG(picker_stat.st_mode),
        "XDPH picker is not a regular file",
    )
    require(
        stat.S_IMODE(picker_stat.st_mode) == 0o755,
        "XDPH picker mode drift",
    )
    require(
        picker_stat.st_uid == expected_owner_uid,
        "XDPH picker is not root-owned",
    )
    picker_text = path.read_text(encoding="utf-8")
    require(
        (
            "guest_looking_glass_linux_capture_output="
            f"'{expected_output}'"
        ) in picker_text,
        "XDPH picker output drift",
    )
    require(
        "'[SELECTION]/screen:%s\\n'" in picker_text,
        "XDPH picker selection protocol drift",
    )
    return picker_text


def pci_class(line: str) -> str:
    fields = line.split()
    require(len(fields) >= 3, f"unexpected lspci row: {line}")
    return fields[1].removesuffix(":").lower()


def main() -> int:
    args = parse_args()
    try:
        repo_root = Path(args.repo_root)
        expected_commit, expected_build = load_expected_pin(repo_root)
        (
            expected_kvmfr_device,
            expected_kvmfr_version,
            expected_patch_sha256,
        ) = load_expected_transport(repo_root)
        (
            expected_capture_output,
            expected_capture_max_fps,
            expected_xdph_picker,
        ) = load_expected_portal(repo_root)
        config = Path(args.config)
        _config_text, sender_uid = load_sender_config(
            config,
            expected_kvmfr_device,
        )
        portal_config = (
            Path(args.portal_config)
            if args.portal_config
            else config.parent / ".config/hypr/xdph.conf"
        )
        load_portal_config(
            portal_config,
            expected_xdph_picker,
            expected_capture_max_fps,
            sender_uid,
        )
        load_capture_picker(
            Path(expected_xdph_picker),
            expected_capture_output,
        )
        nvidia_pci = command("lspci", "-Dn", "-d", "10de:").splitlines()
        classes = {pci_class(line) for line in nvidia_pci}
        require(
            any(value in {"0300", "0302", "0380"} for value in classes),
            "NVIDIA display function is not visible",
        )
        require("0403" in classes, "NVIDIA audio function is not visible")

        ivshmem = command("lspci", "-Dn", "-d", "1af4:1110").splitlines()
        require(ivshmem, "QEMU IVSHMEM PCI device 1af4:1110 is missing")
        ivshmem_driver = command("lspci", "-nnk", "-d", "1af4:1110")
        require(
            "Kernel driver in use: kvmfr" in ivshmem_driver,
            "guest IVSHMEM device is not bound to kvmfr",
        )

        kvmfr_path = Path(expected_kvmfr_device)
        kvmfr_stat = kvmfr_path.stat()
        require(
            stat.S_ISCHR(kvmfr_stat.st_mode),
            "guest kvmfr transport is not a character device",
        )
        require(
            stat.S_IMODE(kvmfr_stat.st_mode) == 0o600,
            "guest kvmfr transport mode drift",
        )
        require_transport_owner(kvmfr_stat.st_uid, sender_uid)
        kvmfr_version = command(
            "modinfo",
            "-F",
            "version",
            "kvmfr",
        )
        require(
            kvmfr_version == expected_kvmfr_version,
            "guest kvmfr module version drift",
        )

        gpu = command(
            "nvidia-smi",
            "--query-gpu=name,driver_version",
            "--format=csv,noheader",
        )
        require(gpu, "nvidia-smi returned no GPU")
        for module in ("nvidia", "nvidia_modeset", "nvidia_uvm", "nvidia_drm"):
            require((Path("/sys/module") / module).is_dir(), f"kernel module is not loaded: {module}")
        for parameter in ("modeset", "fbdev"):
            value = (Path("/sys/module/nvidia_drm/parameters") / parameter).read_text().strip()
            require(value.lower() in {"1", "y"}, f"nvidia_drm {parameter} is disabled")

        sender = Path(args.sender)
        require(sender.is_file() and not sender.is_symlink(), "Linux sender binary is missing")
        require(sender.stat().st_mode & 0o111 != 0, "Linux sender is not executable")
        stamp: Any = yaml.safe_load(Path(args.stamp).read_text(encoding="utf-8"))
        require(isinstance(stamp, dict), "Linux sender stamp is invalid")
        require(stamp.get("commit") == expected_commit, "Linux sender commit pin drift")
        require(stamp.get("build") == expected_build, "Linux sender build pin drift")
        require(
            stamp.get("compat_patch_sha256") == expected_patch_sha256,
            "Linux sender compatibility patch drift",
        )
        require(stamp.get("capture") == "pipewire", "sender was not built for PipeWire")
        require(stamp.get("runtime_enabled") is False, "sender must remain manually gated")
    except (OSError, GateError, yaml.YAMLError) as error:
        print(f"arch-dev-vfio guest gate refused: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "gpu": gpu,
                "nvidia_classes": sorted(classes),
                "nvidia_functions": len(nvidia_pci),
                "ivshmem": ivshmem[0],
                "kvmfr_device": expected_kvmfr_device,
                "kvmfr_version": kvmfr_version,
                "looking_glass_build": expected_build,
                "xdph_capture_output": expected_capture_output,
                "xdph_capture_max_fps": expected_capture_max_fps,
            },
            sort_keys=True,
        )
    )
    print("ARCH_DEV_VFIO_GUEST_GATE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
