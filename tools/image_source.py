#!/usr/bin/env python3
"""Populate source_url, source_checksum_url, and source_sha256 in an image manifest.

Nothing is guessed: the tool downloads the official checksum file, looks for
the exact image filename, and writes only after a match. If the mirror is
unavailable or the filename is absent, it refuses the operation and leaves the
manifest untouched.

  tools/image_source.py debian \\
      https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-generic-amd64.qcow2 \\
      https://cloud.debian.org/images/cloud/bookworm/latest/SHA256SUMS

The second URL is optional. When omitted, the tool tries <url>.SHA256 and then
SHA256SUMS in the same directory.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 30


class Refused(Exception):
    pass


def fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8", "replace")
    except Exception as exc:
        raise Refused(f"unreachable: {url}\n  {exc}") from exc


def find_digest(text: str, filename: str) -> str:
    """Handle two common formats without guessing either one.

      <hash>  <file>              sha256sum / SHA256SUMS style
      SHA256 (<file>) = <hash>    BSD style, also used by Fedora
    """
    for line in text.splitlines():
        line = line.strip()
        bsd = re.match(r"^SHA256\s*\(([^)]+)\)\s*=\s*([0-9a-fA-F]{64})$", line)
        if bsd and Path(bsd.group(1)).name == filename:
            return bsd.group(2).lower()
        plain = re.match(r"^([0-9a-fA-F]{64})\s+[*]?(\S+)$", line)
        if plain and Path(plain.group(2)).name == filename:
            return plain.group(1).lower()
    raise Refused(
        f"'{filename}' does not appear in the checksum file, or the file does "
        "not contain SHA-256 values")


def candidates(url: str) -> list[str]:
    base = url.rsplit("/", 1)[0]
    return [f"{url}.SHA256", f"{url}.sha256",
            f"{base}/SHA256SUMS", f"{base}/CHECKSUM"]


def set_field(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    if not pattern.search(text):
        raise Refused(f"the manifest has no '{key}:' field")
    return pattern.sub(f"{key}: {value}", text, count=1)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    image, url = argv[1], argv[2]
    checksum_url = argv[3] if len(argv) > 3 else None

    manifest = REPO / "images" / f"{image}.yml"
    if not manifest.is_file():
        print(f"REFUSED: manifest not found: {manifest}", file=sys.stderr)
        return 2
    text = manifest.read_text(encoding="utf-8")

    declared = re.search(r"^filename:\s*(\S+)$", text, re.M)
    if not declared:
        print("REFUSED: the manifest does not declare 'filename:'", file=sys.stderr)
        return 1
    upstream_name = url.rsplit("/", 1)[-1]

    try:
        urls = [checksum_url] if checksum_url else candidates(url)
        digest = last = None
        for candidate in urls:
            try:
                digest = find_digest(fetch(candidate), upstream_name)
                checksum_url = candidate
                break
            except Refused as exc:
                last = exc
        if digest is None:
            raise last or Refused("no checksum file was found")

        text = set_field(text, "source_url", url)
        text = set_field(text, "source_checksum_url", checksum_url)
        text = set_field(text, "source_sha256", digest)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    manifest.write_text(text, encoding="utf-8")
    print(f"{image}: source URL and SHA-256 written")
    print(f"  checksum source  {checksum_url}")
    print(f"  sha256            {digest}")
    print(f"  filename          {declared.group(1)} (upstream: {upstream_name})")
    print("\nNext: ansible-playbook playbooks/image-prepare.yml -K "
          f"-e image_id={image}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
