# Pin the reviewed VFIO lifecycle wording and action split in the Control Center.

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = (
    ROOT
    / "roles"
    / "host_desktop_sway"
    / "files"
    / "privatestack-hyperlab-domains.py"
)


def main() -> None:
    source = MANAGER.read_text(encoding="utf-8")

    required = (
        '"vm.managed-reboot"',
        '"vm.power-cycle"',
        '"vm.force-stop"',
        '"Guest OS reboot · QEMU stays running"',
        '"Replace QEMU · reinitialize VFIO devices',
        '"VFIO: Reboot keeps QEMU alive. Use Power cycle if the guest does not recover."',
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise SystemExit("missing VFIO lifecycle UI contract: " + ", ".join(missing))

    print("VFIO lifecycle UX contract: OK")


if __name__ == "__main__":
    main()
