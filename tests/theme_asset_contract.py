#!/usr/bin/env python3
"""Contract for HyperLab Symbols v1."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "themes/assets/hyperlab-symbols-v1"
MANIFEST = ASSETS / "manifest.yml"
THEME = ROOT / "themes/trust-model/theme.yml"

EXPECTED = {
    "01-cerchio-nero-e-rosso.png":
        "f384402336de083018c446921bd9ac34a8605eb05badba7e2b29082d2e6b3e93",
    "02-geometria-blu.png":
        "49a3f12157b045f2260d338777436321fe81ce8dc8db53c0a5f602f7e82616d4",
    "03-orbita-rossa.png":
        "dcc089b8d6ab71dada618ba1f15675b735054f89b03c44833ad320837b2ef954",
    "04-orbita-viola.png":
        "31bc49e57613ee65a73994e6bcda47e8b853eb01ed3c820bd198200f305e6671",
    "05-spirale-verde.png":
        "1985f25f5fcecd85de66d898a291a7387f7f3681a56b4a38f2b911a433622ea6",
    "06-ingranaggio-oro.png":
        "8d6fb22591a5a3d0b7df2410b30c36f356b23b61a97a69b898110d2f5ec9a2c8",
    "07-onda-e-semicerchio.png":
        "25d6e2533cd3c094bd22f7b4cc2ea91b3bdad69af034f2a0abe143298bb4fa70",
    "08-golden-image.png":
        "e49a6b4979fb3d7dea553c485b1170b9841617de649e121efd73592119febcb9",
    "09-vela-geometrica.png":
        "1f79addb2e98547312190d567de60c606b31eaea195f65ba41971fb000ae395b",
    "10-diagramma-circolare.png":
        "ba87056b6085408085b1233bf935b211159693993be707cd59397cc73c864fff",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab asset contract: {message}"
        )


def main() -> int:
    require(MANIFEST.is_file(), "manifest missing")

    doc = yaml.safe_load(
        MANIFEST.read_text(encoding="utf-8")
    )

    require(
        doc["id"] == "hyperlab-symbols-v1",
        "wrong asset-set id",
    )

    require(
        len(doc["images"]) == 10,
        "wrong canonical asset count",
    )

    require(
        doc["semantic_policy"]["trust_assignment"]
        == "pending",
        "trust mapping was invented",
    )

    require(
        doc["semantic_policy"]["theme_assignment"]
        == "pending",
        "theme role was invented",
    )

    for filename, digest in EXPECTED.items():
        path = ASSETS / "images" / filename

        require(path.is_file(), f"missing {filename}")

        observed = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

        require(
            observed == digest,
            f"payload drift: {filename}",
        )

    theme = yaml.safe_load(
        THEME.read_text(encoding="utf-8")
    )

    require(
        theme["wallpaper"]["asset_set"]
        == "hyperlab-trust-v2",
        "trust-model references wrong asset set",
    )

    require(
        theme["selector"]["visible"] is False,
        "unfinished trust-model became selectable",
    )

    result = subprocess.run(
        [
            "python3",
            str(ROOT / "tools/theme_assets.py"),
            "--repo",
            str(ROOT),
            "hyperlab-symbols-v1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    require(
        result.returncode == 0,
        result.stdout + result.stderr,
    )

    print("HyperLab Symbols v1 asset contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
