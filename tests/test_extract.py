"""Document to plain text."""

from __future__ import annotations

from pathlib import Path

import pytest

from iroha_reader_cli.errors import ReaderError, UnsupportedInputError
from iroha_reader_cli.extract import (
    extract,
    parse_page_range,
    read_text_file,
    strip_markdown,
)


def test_strip_markdown_drops_code_blocks_by_default() -> None:
    text = strip_markdown("Intro.\n\n```py\nprint(1)\n```\n")
    assert "print(1)" not in text
    assert "Intro." in text


def test_keep_code_keeps_the_code_lines() -> None:
    text = strip_markdown("```py\nprint(1)\n```\n", keep_code=True)
    assert "print(1)" in text
    assert "```" not in text


def test_strip_markdown_unwraps_links_headings_and_emphasis() -> None:
    text = strip_markdown("# Title\n\n- **bold** [label](http://x) `code`\n")
    assert "Title" in text
    assert "bold label code" in text
    assert "http://x" not in text
    assert "#" not in text


def test_read_text_file_falls_back_to_cp932(tmp_path: Path) -> None:
    path = tmp_path / "old.txt"
    path.write_bytes("日本語".encode("cp932"))
    assert read_text_file(path) == "日本語"


def test_read_text_file_strips_the_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbfhello")
    assert read_text_file(path) == "hello"


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("3-10", (3, 10)), ("5", (5, 5)), ("3-", (3, None)), (" 2 - 4 ", (2, 4))],
)
def test_parse_page_range(spec: str, expected: tuple[int, int | None]) -> None:
    assert parse_page_range(spec) == expected


@pytest.mark.parametrize("spec", ["0", "10-3", "a-b", "", "-"])
def test_parse_page_range_rejects_nonsense(spec: str) -> None:
    with pytest.raises(ReaderError, match="bad page range"):
        parse_page_range(spec)


def test_extract_reports_an_unknown_suffix(tmp_path: Path) -> None:
    path = tmp_path / "notes.docx"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedInputError, match="unsupported file type"):
        extract(path)


def test_extract_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="file not found"):
        extract(tmp_path / "gone.md")


def test_extract_reads_markdown_and_text(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("# Head\n\nBody.\n", encoding="utf-8")
    assert "Body." in extract(md)
    txt = tmp_path / "a.txt"
    txt.write_text("Plain.\n", encoding="utf-8")
    assert extract(txt) == "Plain.\n"


def test_pdf_page_range_is_checked(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    path = tmp_path / "one.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(ReaderError, match="past the end"):
        extract(path, pages=(5, None))
    assert extract(path, pages=(1, None)).strip() == ""
