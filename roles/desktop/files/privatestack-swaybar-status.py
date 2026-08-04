#!/usr/bin/env python3
"""Native swaybar status stream with click actions for HyperLab."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Any, Callable

HOME = Path.home()
THEME_FILE = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "hyperlab/theme"

PALETTES: dict[str, dict[str, str]] = {
    "green": {"base":"#0c1512","mantle":"#111d18","surface":"#1a2b23","overlay":"#2b453a","text":"#dcf3e4","subtext":"#93b3a3","accent":"#7ee787","accent2":"#35e4dd","ok":"#72f2a5","warn":"#ffd275","bad":"#ff668f"},
    "violet": {"base":"#0a0a16","mantle":"#12122a","surface":"#1b1b3a","overlay":"#2f2f5c","text":"#e2e0ff","subtext":"#9d9dc4","accent":"#9d6cff","accent2":"#43d8ff","ok":"#72f2a5","warn":"#ffd275","bad":"#ff668f"},
    "blue": {"base":"#08131f","mantle":"#0d1c2b","surface":"#142a3e","overlay":"#254866","text":"#deefff","subtext":"#8eacc4","accent":"#4da3ff","accent2":"#55d6ff","ok":"#62d9a6","warn":"#ffd166","bad":"#ff6b7a"},
    "red": {"base":"#180b0d","mantle":"#241013","surface":"#35171b","overlay":"#5a2a31","text":"#ffe7e9","subtext":"#c49a9f","accent":"#ff5d6c","accent2":"#ff9f43","ok":"#72f2a5","warn":"#ffd166","bad":"#ff3d5a"},
}
WALLPAPER_MODE_FILE = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "hyperlab/wallpaper-mode"
KEYBOARD_LAYOUT_FILE = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "hyperlab/keyboard-layout"


def current_theme() -> str:
    try:
        theme = THEME_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        theme = "green"
    return theme if theme in PALETTES else "green"


def current_wallpaper_mode() -> str:
    try:
        mode = WALLPAPER_MODE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        mode = "public"
    return mode if mode in {"public", "personal"} else "public"



def current_keyboard_layout() -> str:
    try:
        layout = KEYBOARD_LAYOUT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        layout = "it"
    return layout if layout in {"it", "us", "ara"} else "it"


def keyboard_label() -> str:
    return {"it": "IT", "us": "EN", "ara": "AR"}[current_keyboard_layout()]


def run_text(argv: list[str], timeout: float = 1.2) -> str:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def spawn(argv: list[str]) -> None:
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class TimedValue:
    def __init__(self, interval: float, reader: Callable[[], str], fallback: str) -> None:
        self.interval = interval
        self.reader = reader
        self.value = fallback
        self.updated = 0.0

    def get(self) -> str:
        now = time.monotonic()
        if now - self.updated >= self.interval:
            value = self.reader()
            if value:
                self.value = value
            self.updated = now
        return self.value


def read_vms() -> str:
    output = run_text(["virsh", "-c", "qemu:///system", "list", "--state-running", "--name"])
    count = len([line for line in output.splitlines() if line.strip()])
    return f"VM {count}"


def read_gpu() -> str:
    count = len(glob.glob("/sys/bus/pci/drivers/vfio-pci/0000:*"))
    return f"VFIO {count}" if count else "GPU host"


def read_network() -> str:
    interface = ""
    try:
        for line in Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]:
            fields = line.split()
            if len(fields) > 1 and fields[1] == "00000000":
                interface = fields[0]
                break
    except OSError:
        pass
    if not interface:
        return "offline"
    try:
        state = Path(f"/sys/class/net/{interface}/operstate").read_text(encoding="utf-8").strip()
    except OSError:
        state = "unknown"
    return interface if state == "up" else "offline"



def read_temperature() -> str:
    values: list[int] = []
    for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        try:
            raw = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        value = raw // 1000 if raw > 1000 else raw
        if 0 < value < 150:
            values.append(value)
    return f"TEMP {max(values)}°C" if values else "TEMP ?"


def read_volume() -> str:
    value = run_text(["pamixer", "--get-volume-human"])
    return f"VOL {value}" if value else "VOL ?"


def read_battery() -> str:
    batteries = sorted(Path("/sys/class/power_supply").glob("BAT*"))
    if not batteries:
        return "AC"
    try:
        capacity = (batteries[0] / "capacity").read_text(encoding="utf-8").strip()
        status = (batteries[0] / "status").read_text(encoding="utf-8").strip().lower()
    except OSError:
        return "BAT ?"
    mark = "+" if status == "charging" else ""
    return f"BAT {mark}{capacity}%"


VMS = TimedValue(5.0, read_vms, "VM ?")
GPU = TimedValue(10.0, read_gpu, "GPU ?")
NETWORK = TimedValue(5.0, read_network, "NET ?")
VOLUME = TimedValue(2.0, read_volume, "VOL ?")
BATTERY = TimedValue(15.0, read_battery, "BAT ?")
TEMPERATURE = TimedValue(5.0, read_temperature, "TEMP ?")


def block(name: str, text: str, palette: dict[str, str], *, accent: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "instance": name,
        "full_text": f" {text} ",
        "color": palette["base"] if accent else palette["text"],
        "background": palette["accent"] if accent else palette["mantle"],
        "border": palette["accent2"] if accent else palette["overlay"],
        "border_top": 1,
        "border_right": 1,
        "border_bottom": 1,
        "border_left": 1,
        "separator": False,
        "separator_block_width": 4,
        "markup": "none",
    }


def blocks() -> list[dict[str, Any]]:
    theme = current_theme()
    palette = PALETTES[theme]
    now = time.strftime("%a %d %b  %H:%M")
    return [
        block("brand", "HyperLab", palette, accent=True),
        block("theme", theme.upper(), palette, accent=True),
        block("wallpaper", "CHILL" if current_wallpaper_mode() == "public" else "PERSONAL", palette),
        block("keyboard", f"KEY {keyboard_label()}", palette),
        block("controls", "CONTROLS", palette),
        block("vms", VMS.get(), palette),
        block("gpu", GPU.get(), palette),
        block("network", NETWORK.get(), palette),
        block("volume", VOLUME.get(), palette),
        block("temperature", TEMPERATURE.get(), palette),
        block("battery", BATTERY.get(), palette),
        block("clock", now, palette),
    ]


def handle_event(event: dict[str, Any]) -> None:
    name = str(event.get("name", ""))
    button = int(event.get("button", 0) or 0)

    if name == "theme":
        if button == 1:
            spawn(["/usr/local/bin/privatestack-theme", "cycle"])
        elif button == 3:
            spawn(["/usr/local/bin/privatestack-theme", "next"])
        return

    if name == "wallpaper" and button == 1:
        spawn(["/usr/local/bin/privatestack-theme", "mode-toggle"])
        return

    if name == "keyboard":
        if button == 1:
            spawn(["/usr/local/bin/privatestack-keyboard", "cycle"])
        elif button == 3:
            spawn(["/usr/local/bin/privatestack-controls", "keyboard"])
        return

    if name == "controls" and button == 1:
        spawn(["/usr/local/bin/privatestack-controls", "menu"])
        return

    if name in {"brand", "vms"}:
        if button == 1:
            spawn(["/usr/local/bin/privatestack-hyperlab-domains", "--surface", "overlay", "--section", "vms"])
        elif button == 3:
            spawn(["/usr/local/bin/privatestack-hyperlab-domains", "--surface", "overlay", "--section", "diagnostics"])
        return

    if name == "gpu" and button == 1:
        spawn(["/usr/local/bin/privatestack-hyperlab-domains", "--surface", "overlay", "--section", "diagnostics"])
    elif name == "network" and button == 1:
        spawn(["foot", "--app-id=floatterm", "nmtui"])
    elif name == "volume":
        if button == 1:
            spawn(["pamixer", "-t"])
        elif button == 4:
            spawn(["pamixer", "-i", "5"])
        elif button == 5:
            spawn(["pamixer", "-d", "5"])


def event_reader(events: queue.SimpleQueue[dict[str, Any]]) -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw or raw in {"[", "]"}:
            continue
        if raw.startswith(","):
            raw = raw[1:].lstrip()
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.put(event)


def main() -> int:
    events: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
    threading.Thread(target=event_reader, args=(events,), daemon=True).start()

    print(json.dumps({"version": 1, "click_events": True}), flush=True)
    print("[", flush=True)
    first = True

    while True:
        while True:
            try:
                handle_event(events.get_nowait())
            except queue.Empty:
                break
        prefix = "" if first else ","
        print(prefix + json.dumps(blocks(), ensure_ascii=False), flush=True)
        first = False
        time.sleep(1)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0) from None
