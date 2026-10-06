#!/usr/bin/python3
"""hyperlab-safe-pdf - a PDF rebuilt from pixels only (ADR 0051).

  to-pixels PDF        in a disposable Machine without a network: render
                       every page with pdftoppm and write the pixel stream
                       to standard output
  from-pixels OUTPUT   in the Machine that asked: read a pixel stream from
                       standard input and write a new PDF made of one image
                       per page

The pixel stream is the only thing that crosses back, and its reader trusts
none of it. It is a fixed header, then for each page its width, height and
exactly width x height x 3 bytes of RGB, then an end line; every number has
a limit, and anything else ends the read with nothing written. Whatever the
original PDF carried (scripts, forms, fonts, links, embedded files) stays in
the disposable Machine, which is discarded.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

MAGIC = b"HLPX1"
DPI_RANGE = (50, 600)
DEFAULT_DPI = 150
MAX_PAGES = 1000
MAX_SIDE = 10000
MAX_PAGE_PIXELS = 40_000_000
MAX_TOTAL_PIXELS = 1_000_000_000
LINE_LIMIT = 40
CHUNK = 1 << 20


class Refused(ValueError):
    pass


def read_line(stream) -> bytes:
    line = stream.readline(LINE_LIMIT)
    if not line.endswith(b"\n"):
        raise Refused("a header line is missing, too long or cut short")
    return line[:-1]


def read_pixels(stream, sink):
    """Validate a pixel stream; hand each page to sink(width, height, chunks).

    Returns (dpi, pages). Raises Refused on anything outside the format.
    """
    header = re.fullmatch(rb"HLPX1 ([0-9]{2,3})", read_line(stream))
    if header is None:
        raise Refused("not a pixel stream")
    dpi = int(header.group(1))
    if not DPI_RANGE[0] <= dpi <= DPI_RANGE[1]:
        raise Refused("resolution %d dpi is out of range" % dpi)
    pages = 0
    total = 0
    while True:
        line = read_line(stream)
        if line == b"END":
            break
        page = re.fullmatch(rb"PAGE ([1-9][0-9]{0,4}) ([1-9][0-9]{0,4})", line)
        if page is None:
            raise Refused("a page header is malformed")
        width, height = int(page.group(1)), int(page.group(2))
        if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PAGE_PIXELS:
            raise Refused("page %d is too large: %dx%d" % (pages + 1, width, height))
        pages += 1
        total += width * height
        if pages > MAX_PAGES or total > MAX_TOTAL_PIXELS:
            raise Refused("the document is too large")
        remaining = width * height * 3

        def chunks(remaining=remaining):
            while remaining:
                data = stream.read(min(CHUNK, remaining))
                if not data:
                    raise Refused("a page is cut short")
                remaining -= len(data)
                yield data

        sink(width, height, chunks())
    if stream.read(1):
        raise Refused("data after the end line")
    if pages == 0:
        raise Refused("no pages")
    return dpi, pages


def write_pdf(output: Path, dpi: int, pages: list[tuple[int, int, Path]]) -> None:
    """A PDF of one Flate-compressed RGB image per page, nothing else."""
    offsets = []
    with open(output, "wb") as out:
        def obj(body_head: bytes, stream_path: Path | None = None) -> None:
            offsets.append(out.tell())
            out.write(b"%d 0 obj\n" % len(offsets))
            out.write(body_head)
            if stream_path is not None:
                out.write(b"\nstream\n")
                with open(stream_path, "rb") as data:
                    while block := data.read(CHUNK):
                        out.write(block)
                out.write(b"\nendstream")
            out.write(b"\nendobj\n")

        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        kids = b" ".join(b"%d 0 R" % (3 + 3 * index) for index in range(len(pages)))
        obj(b"<< /Type /Catalog /Pages 2 0 R >>")
        obj(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages)))
        for index, (width, height, data_path) in enumerate(pages):
            page_obj = 3 + 3 * index
            points_w = width * 72 / dpi
            points_h = height * 72 / dpi
            content = b"q %.2f 0 0 %.2f 0 0 cm /Im0 Do Q" % (points_w, points_h)
            obj(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R "
                b"/Resources << /XObject << /Im0 %d 0 R >> >> >>"
                % (points_w, points_h, page_obj + 1, page_obj + 2))
            offsets.append(out.tell())
            out.write(b"%d 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n"
                      % (len(offsets), len(content), content))
            obj(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
                b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>"
                % (width, height, data_path.stat().st_size), data_path)
        xref = out.tell()
        out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(offsets) + 1))
        for offset in offsets:
            out.write(b"%010d 00000 n \n" % offset)
        out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                  % (len(offsets) + 1, xref))


def from_pixels(stream, output: Path) -> int:
    """Rebuild OUTPUT from a pixel stream; nothing is written unless it is whole."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise Refused("%s exists; choose a new name" % output)
    with tempfile.TemporaryDirectory(prefix="hyperlab-safe-pdf-") as work:
        work = Path(work)
        pages = []

        def sink(width, height, chunks):
            path = work / ("page-%04d" % (len(pages) + 1))
            packer = zlib.compressobj(6)
            with open(path, "wb") as out:
                for data in chunks:
                    out.write(packer.compress(data))
                out.write(packer.flush())
            pages.append((width, height, path))

        dpi, count = read_pixels(stream, sink)
        partial = work / "out.pdf"
        write_pdf(partial, dpi, pages)
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "wb") as final, open(partial, "rb") as source:
            while block := source.read(CHUNK):
                final.write(block)
    return count


def read_ppm(path: Path):
    """pdftoppm's own P6 output, inside the disposable Machine."""
    with open(path, "rb") as data:
        head = b""
        while head.count(b"\n") < 3 and len(head) < 64:
            head += data.read(1)
        match = re.fullmatch(rb"P6\n([0-9]+) ([0-9]+)\n255\n", head)
        if match is None:
            raise Refused("unexpected pdftoppm output in %s" % path.name)
        width, height = int(match.group(1)), int(match.group(2))
        return width, height, data.read()


def to_pixels(pdf: Path, out, dpi: int = DEFAULT_DPI, run=subprocess.run) -> int:
    with tempfile.TemporaryDirectory(prefix="hyperlab-pixels-") as work:
        result = run(["pdftoppm", "-r", str(dpi), "--", str(pdf), str(Path(work) / "page")],
                     capture_output=True, check=False)
        if result.returncode != 0:
            raise Refused("pdftoppm could not render the document")
        pages = sorted(Path(work).glob("page-*.ppm"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        if not pages:
            raise Refused("the document has no pages")
        out.write(b"HLPX1 %d\n" % dpi)
        for page in pages:
            width, height, pixels = read_ppm(page)
            out.write(b"PAGE %d %d\n" % (width, height))
            out.write(pixels)
        out.write(b"END\n")
        out.flush()
        return len(pages)


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 2 and argv[0] == "to-pixels":
            to_pixels(Path(argv[1]), sys.stdout.buffer)
            return 0
        if len(argv) == 2 and argv[0] == "from-pixels":
            count = from_pixels(sys.stdin.buffer, Path(argv[1]))
            print("hyperlab-safe-pdf: %d page(s) written to %s" % (count, argv[1]), file=sys.stderr)
            return 0
    except (Refused, OSError) as exc:
        print("hyperlab-safe-pdf: refused: %s" % exc, file=sys.stderr)
        return 1
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
