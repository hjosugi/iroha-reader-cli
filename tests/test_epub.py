"""Reading an epub."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from conftest import write_epub
from iroha_reader_cli import epub
from iroha_reader_cli.errors import ReaderError

CHAPTER_ONE = """<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>ignore me</title><style>p { color: red }</style></head>
<body>
  <h1>Chapter One</h1>
  <p>The first paragraph &amp; its ampersand.</p>
  <p>Second paragraph<br/>with a break.</p>
  <ul><li>a list item</li></ul>
  <script>ignored()</script>
</body></html>"""

CHAPTER_TWO = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
  <h2>Chapter Two</h2><p>It ends here.</p>
</body></html>"""


@pytest.fixture
def book(tmp_path: Path) -> Path:
    return write_epub(tmp_path / "book.epub",
                      [("ch1.xhtml", CHAPTER_ONE), ("ch2.xhtml", CHAPTER_TWO)])


def test_blocks_follow_the_spine_and_keep_headings(book: Path) -> None:
    blocks = epub.extract_blocks(book)
    assert [(b.heading, b.text) for b in blocks] == [
        (1, "Chapter One"),
        (None, "The first paragraph & its ampersand."),
        (None, "Second paragraph with a break."),
        (None, "a list item"),
        (2, "Chapter Two"),
        (None, "It ends here."),
    ]


def test_scripts_styles_and_titles_are_left_out(book: Path) -> None:
    text = " ".join(block.text for block in epub.extract_blocks(book))
    assert "ignored()" not in text
    assert "color: red" not in text
    assert "ignore me" not in text


def test_the_spine_decides_the_order(tmp_path: Path) -> None:
    path = write_epub(tmp_path / "b.epub",
                      [("second.xhtml", "<p>Second</p>"), ("first.xhtml", "<p>First</p>")])
    assert [b.text for b in epub.extract_blocks(path)] == ["Second", "First"]


def test_a_file_that_is_not_a_zip(tmp_path: Path) -> None:
    path = tmp_path / "fake.epub"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(ReaderError, match="as an epub"):
        epub.extract_blocks(path)


def test_a_zip_without_a_container(tmp_path: Path) -> None:
    path = tmp_path / "bare.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
    with pytest.raises(ReaderError, match=r"no container\.xml"):
        epub.extract_blocks(path)


def test_a_container_without_a_package(tmp_path: Path) -> None:
    path = write_epub(tmp_path / "b.epub", [("a.xhtml", "<p>x</p>")],
                      container='<?xml version="1.0"?><container/>')
    with pytest.raises(ReaderError, match="names no package file"):
        epub.extract_blocks(path)


def test_an_empty_spine(tmp_path: Path) -> None:
    path = write_epub(
        tmp_path / "b.epub", [("a.xhtml", "<p>x</p>")],
        opf='<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf">'
            "<manifest/><spine/></package>",
    )
    with pytest.raises(ReaderError, match="no readable chapters"):
        epub.extract_blocks(path)


def test_html_blocks_handles_nested_markup() -> None:
    blocks = epub.html_blocks(
        "<div><p>Some <em>emphasis</em> and <b>bold</b>.</p>"
        "<blockquote>A quote.</blockquote></div>"
    )
    assert [b.text for b in blocks] == ["Some emphasis and bold.", "A quote."]


def test_extract_dispatches_on_the_suffix(book: Path) -> None:
    from iroha_reader_cli import extract

    assert ".epub" in extract.SUPPORTED_SUFFIXES
    blocks = extract.extract_blocks(book)
    assert blocks[0].heading == 1
    assert "Chapter One" in extract.extract(book)


def test_a_missing_epub_says_so(tmp_path: Path) -> None:
    from iroha_reader_cli import extract

    with pytest.raises(ReaderError, match="file not found"):
        extract.extract_blocks(tmp_path / "gone.epub")
