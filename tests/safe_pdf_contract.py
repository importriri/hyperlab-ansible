#!/usr/bin/env python3
"""A PDF rebuilt from pixels keeps the pages and nothing else (ADR 0051).

  1. A pixel stream becomes a PDF that stores exactly those pixels, one
     lossless image per page at the stream's resolution, and renders back
     to the same picture (poppler smooths when it renders, so the picture
     is compared pixel by pixel, most within 4 levels).
  2. A PDF carrying JavaScript, an embedded file, a link and a form, sent
     through to-pixels and from-pixels, comes back with the same picture and
     none of them.
  3. The reader refuses, and writes nothing, for: another format, a
     resolution out of range, a page too large, too many pages, a page cut
     short, data after the end, no pages, an overlong header line, and an
     output that already exists.

pdftoppm and pdfinfo (poppler) must be installed: CI installs them, and
the disposable viewer uses the same pdftoppm.
"""

from __future__ import annotations

import importlib.util
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("safe_pdf", ROOT / "roles/guest_safe_documents/files/hyperlab-safe-pdf.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def stream(pages, dpi=150, tail=b"END\n"):
    data = b"HLPX1 %d\n" % dpi
    for width, height, pixels in pages:
        data += b"PAGE %d %d\n" % (width, height) + pixels
    return data + tail


def pattern(width, height, seed):
    return bytes((x * 7 + y * 13 + seed * 31 + channel * 50) % 256
                 for y in range(height) for x in range(width) for channel in range(3))


def stored_images(pdf: Path):
    """Each image XObject's decompressed bytes, from the PDF this tool writes."""
    data = pdf.read_bytes()
    found = []
    for match in re.finditer(rb"/Width (\d+) /Height (\d+) .*?/Length (\d+) >>\nstream\n", data):
        start = match.end()
        found.append((int(match.group(1)), int(match.group(2)),
                      zlib.decompress(data[start:start + int(match.group(3))])))
    return found


def close(left, right, share=0.8):
    """Same page sizes, and most pixels within 4 levels: poppler blends edges."""
    if [(w, h) for w, h, _ in left] != [(w, h) for w, h, _ in right]:
        return False
    for (_, _, a), (_, _, b) in zip(left, right):
        same = sum(1 for i in range(0, len(a), 3) if max(abs(a[i + c] - b[i + c]) for c in range(3)) <= 4)
        if same < share * len(a) / 3:
            return False
    return True


def blocks(width, height, seed):
    """Flat 10x10 colour blocks: a picture smoothing barely changes."""
    return bytes(((x // 10) * 60 + seed * 40 + channel * 70) % 256 if (y // 10) % 2 else (y // 10) * 50 % 256
                 for y in range(height) for x in range(width) for channel in range(3))


def rendered(pdf: Path, dpi: int, work: Path):
    out = io.BytesIO()
    S.to_pixels(pdf, out, dpi=dpi)
    found = []
    S.read_pixels(io.BytesIO(out.getvalue()),
                  lambda w, h, chunks: found.append((w, h, b"".join(chunks))))
    return found


def malicious_pdf(path: Path) -> None:
    """One page with a blue square, plus everything the rebuild must drop."""
    content = b"0 0 1 rg 20 20 60 60 re f"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R /OpenAction 4 0 R /AcroForm << /Fields [6 0 R] >> "
        b"/Names << /EmbeddedFiles << /Names [(payload.sh) 7 0 R] >> >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents 5 0 R "
        b"/Annots [<< /Type /Annot /Subtype /Link /Rect [0 0 100 100] "
        b"/A << /S /URI /URI (http://evil.example/) >> >>] >>",
        b"<< /S /JavaScript /JS (app.alert('pwned')) >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /FT /Tx /T (secret) /V (x) >>",
        b"<< /Type /Filespec /F (payload.sh) /EF << /F 8 0 R >> >>",
        b"<< /Type /EmbeddedFile /Length 9 >>\nstream\nrm -rf ~\n\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))


def check_roundtrip(work: Path) -> None:
    pages = [(200, 150, blocks(200, 150, 1)), (150, 250, blocks(150, 250, 2))]
    output = work / "rebuilt.pdf"
    require(S.from_pixels(io.BytesIO(stream(pages, dpi=72)), output) == 2, "two pages were not written")
    info = subprocess.run(["pdfinfo", str(output)], capture_output=True, text=True, check=True).stdout
    require(re.search(r"^Pages:\s+2$", info, re.M), f"pdfinfo does not see two pages: {info}")
    require(re.search(r"^Page size:\s+200 x 150 pts", info, re.M), f"the page size is not the stream's: {info}")
    output_150 = work / "rebuilt-150.pdf"
    S.from_pixels(io.BytesIO(stream(pages[:1], dpi=150)), output_150)
    info = subprocess.run(["pdfinfo", str(output_150)], capture_output=True, text=True, check=True).stdout
    require(re.search(r"^Page size:\s+96 x 72 pts", info, re.M), f"150 dpi is not honoured: {info}")
    require(stored_images(output) == pages, "the rebuilt PDF does not store exactly the stream's pixels")
    require(close(rendered(output, 72, work), pages), "the rebuilt pages do not render back to the same picture")


def check_malicious(work: Path) -> None:
    source = work / "attachment.pdf"
    malicious_pdf(source)
    original = rendered(source, 72, work)
    require(len(original) == 1 and original[0][:2] == (100, 100), "the crafted PDF did not render")
    pixels = io.BytesIO()
    S.to_pixels(source, pixels, dpi=72)
    output = work / "safe.pdf"
    S.from_pixels(io.BytesIO(pixels.getvalue()), output)
    data = output.read_bytes()
    for name in (b"/JavaScript", b"/JS", b"/EmbeddedFile", b"/URI", b"/AcroForm", b"/Annots", b"/OpenAction",
                 b"payload", b"evil.example", b"rm -rf"):
        require(name not in data, f"the rebuilt PDF still carries {name!r}")
    require(close(rendered(output, 72, work), original), "the rebuilt PDF does not look like the original")


def check_refusals(work: Path) -> None:
    page = (4, 3, pattern(4, 3, 0))
    cases = {
        "another format": b"%PDF-1.4\n",
        "a resolution out of range": stream([page], dpi=20),
        "a page too large": b"HLPX1 150\nPAGE 10001 1\n",
        "a page with too many pixels": b"HLPX1 150\nPAGE 8000 8000\n",
        "a page cut short": stream([page])[:-10],
        "data after the end": stream([page]) + b"x",
        "no pages": b"HLPX1 150\nEND\n",
        "an overlong header line": b"HLPX1 150\nPAGE " + b"1" * 60 + b"\n",
        "a missing end": stream([page], tail=b""),
        "a page header with a sign": b"HLPX1 150\nPAGE -4 3\n",
    }
    for label, data in cases.items():
        output = work / "refused.pdf"
        try:
            S.from_pixels(io.BytesIO(data), output)
        except S.Refused:
            pass
        else:
            raise AssertionError(f"the reader accepted {label}")
        require(not output.exists(), f"something was written for {label}")

    limit = S.MAX_PAGES
    S.MAX_PAGES = 2
    try:
        S.from_pixels(io.BytesIO(stream([page] * 3)), work / "many.pdf")
    except S.Refused:
        pass
    else:
        raise AssertionError("the reader accepted too many pages")
    finally:
        S.MAX_PAGES = limit
    require(not (work / "many.pdf").exists(), "something was written for too many pages")

    existing = work / "existing.pdf"
    existing.write_bytes(b"keep")
    try:
        S.from_pixels(io.BytesIO(stream([page])), existing)
    except S.Refused:
        pass
    else:
        raise AssertionError("an existing output was overwritten")
    require(existing.read_bytes() == b"keep", "an existing output was changed")

    result = subprocess.run([sys.executable, str(ROOT / "roles/guest_safe_documents/files/hyperlab-safe-pdf.py"),
                             "from-pixels", str(work / "cli.pdf")], input=b"junk\n", capture_output=True, check=False)
    require(result.returncode == 1 and b"refused" in result.stderr and not (work / "cli.pdf").exists(),
            "the command line does not refuse a bad stream")


def main() -> int:
    for tool in ("pdftoppm", "pdfinfo"):
        require(shutil.which(tool) is not None, f"{tool} is missing: install poppler")
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        check_roundtrip(work)
        check_malicious(work)
        check_refusals(work)
    print("Safe PDF contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
