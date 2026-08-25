"""Shared test helpers."""

from __future__ import annotations

import shutil
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
