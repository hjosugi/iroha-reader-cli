"""Shared test helpers."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never touch the developer's real segment cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def _have(*commands: str) -> bool:
    return all(shutil.which(c) is not None for c in commands)


requires_ffmpeg = pytest.mark.skipif(
    not _have("ffmpeg", "ffprobe"), reason="needs ffmpeg and ffprobe"
)
requires_espeak = pytest.mark.skipif(
    not _have("espeak-ng"), reason="needs espeak-ng"
)
requires_pdftotext = pytest.mark.skipif(
    not _have("pdftotext"), reason="needs poppler-utils"
)


def write_pdf(path: Path, pages: list[list[str]]) -> Path:
    """Write a minimal one-font pdf, one text line per string."""
    contents = []
    for lines in pages:
        parts = ["BT", "/F1 11 Tf"]
        for index, line in enumerate(lines):
            parts.append(f"1 0 0 1 60 {720 - index * 20} Tm ({line}) Tj")
        parts.append("ET")
        contents.append("\n".join(parts).encode("ascii"))

    objects: list[bytes] = [b"", b"", b"", b"<< /Type /Font /Subtype /Type1 "
                            b"/BaseFont /Helvetica >>"]
    page_ids = [5 + index * 2 for index in range(len(contents))]
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objects[1] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(contents)
    objects[2] = b"<< >>"  # placeholder, keeps the numbering simple
    for index, content in enumerate(contents):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
            b"<< /Font << /F1 4 0 R >> >> /Contents %d 0 R >>" % (page_ids[index] + 1)
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content
                       + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1) + b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref_at)
    path.write_bytes(bytes(out))
    return path


EPUB_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def write_epub(path: Path, documents: list[tuple[str, str]],
               container: str = EPUB_CONTAINER, opf: str | None = None) -> Path:
    """Write a minimal epub. `documents` are (file name, xhtml) pairs."""
    items = "\n".join(
        f'<item id="d{index}" href="{name}" media-type="application/xhtml+xml"/>'
        for index, (name, _) in enumerate(documents)
    )
    spine = "\n".join(f'<itemref idref="d{index}"/>'
                       for index in range(len(documents)))
    package = opf if opf is not None else f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>A Small Book</dc:title>
  </metadata>
  <manifest>
    {items}
    <item id="css" href="style.css" media-type="text/css"/>
  </manifest>
  <spine>
    {spine}
  </spine>
</package>"""

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/book.opf", package)
        archive.writestr("OEBPS/style.css", "p { color: red }")
        for name, html in documents:
            archive.writestr(f"OEBPS/{name}", html)
    return path
