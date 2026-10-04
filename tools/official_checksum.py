#!/usr/bin/env python3
"""Check one artefact against the vendor's own checksum file.

Distributions publish checksums in two shapes, with SHA-256 or SHA-512:

  GNU  <hex>  <name>                 Arch .SHA256, Debian SHA512SUMS
  BSD  SHA256 (<name>) = <hex>       Fedora CHECKSUM

The file is searched for exactly the expected basename; the algorithm comes
from the BSD tag or from the length of the digest. Zero entries, conflicting
entries or a different digest are refusals. Signature lines (PGP armour,
comments) are ignored, not trusted: this tool checks a digest, it does not
verify a signature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

GNU = re.compile(r"^(?P<digest>[0-9a-fA-F]{64}|[0-9a-fA-F]{128}) [ *](?P<name>\S+)$")
BSD = re.compile(r"^(?P<algorithm>SHA256|SHA512) \((?P<name>[^)]+)\) = (?P<digest>[0-9a-fA-F]+)$")
LENGTHS = {64: "sha256", 128: "sha512"}
CHUNK = 1 << 20


class ChecksumError(ValueError):
    pass


def entries_for(text: str, basename: str) -> set[tuple[str, str]]:
    found = set()
    for raw in text.splitlines():
        line = raw.strip()
        match = BSD.fullmatch(line)
        if match:
            algorithm = match.group("algorithm").lower()
            digest = match.group("digest").lower()
            if LENGTHS.get(len(digest)) != algorithm:
                raise ChecksumError(f"malformed {algorithm} entry for {match.group('name')}")
        else:
            match = GNU.fullmatch(line)
            if not match:
                continue
            digest = match.group("digest").lower()
            algorithm = LENGTHS[len(digest)]
        if match.group("name") == basename:
            found.add((algorithm, digest))
    return found


def expected_digest(text: str, basename: str) -> tuple[str, str]:
    found = entries_for(text, basename)
    if not found:
        raise ChecksumError(f"the official checksum file has no entry for {basename}")
    if len(found) > 1:
        raise ChecksumError(f"the official checksum file has conflicting entries for {basename}")
    return next(iter(found))


def digest_of(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def check(checksums: Path, basename: str, artifact: Path) -> dict:
    if Path(basename).name != basename or not basename:
        raise ChecksumError("the expected name must be one basename")
    algorithm, expected = expected_digest(checksums.read_text(encoding="utf-8", errors="replace"), basename)
    observed = digest_of(artifact, algorithm)
    if observed != expected:
        raise ChecksumError(f"{artifact} does not match the official {algorithm} of {basename}")
    return {"basename": basename, "algorithm": algorithm, "digest": observed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checksums", required=True, type=Path)
    parser.add_argument("--basename", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args()
    if args.artifact.is_symlink() or not args.artifact.is_file():
        print("the artefact must be one regular file", file=sys.stderr)
        return 2
    try:
        print(json.dumps(check(args.checksums, args.basename, args.artifact)))
    except (OSError, ChecksumError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
