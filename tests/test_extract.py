"""Document to plain text."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import write_pdf
from iroha_reader_cli import extract as extract_module
from iroha_reader_cli.errors import (
    MissingCommandError,
    ReaderError,
    UnsupportedInputError,
)
from iroha_reader_cli.extract import (
    extract,
    extract_pdf,
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


def sample_pdf(tmp_path: Path) -> Path:
    return write_pdf(
        tmp_path / "doc.pdf",
        [["Page one line one.", "Page one line two."], ["Page two only line."]],
    )


@pytest.mark.parametrize("backend", ["pypdf", "pdftotext"])
def test_both_pdf_backends_read_the_text(tmp_path: Path, backend: str) -> None:
    if backend == "pdftotext" and shutil.which("pdftotext") is None:
        pytest.skip("needs poppler-utils")
    text = extract_pdf(sample_pdf(tmp_path), backend=backend)
    assert "Page one line one." in text
    assert "Page two only line." in text


@pytest.mark.parametrize("backend", ["pypdf", "pdftotext"])
def test_both_pdf_backends_honour_a_page_range(tmp_path: Path, backend: str) -> None:
    if backend == "pdftotext" and shutil.which("pdftotext") is None:
        pytest.skip("needs poppler-utils")
    text = extract_pdf(sample_pdf(tmp_path), pages=(2, None), backend=backend)
    assert "Page two only line." in text
    assert "Page one" not in text


def test_pypdf_reports_a_page_past_the_end(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="past the end"):
        extract_pdf(sample_pdf(tmp_path), pages=(5, None), backend="pypdf")


def test_auto_prefers_pdftotext_when_poppler_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], _stdin: bytes | None = None) -> _Output:
        seen.append(argv)
        return _Output()

    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/pdftotext")
    monkeypatch.setattr(extract_module, "run", fake_run)
    extract_pdf(sample_pdf(tmp_path))
    assert seen and seen[0][0] == "pdftotext"
    # No -layout: the default mode is the one that undoes columns.
    assert "-layout" not in seen[0]


def test_auto_falls_back_to_pypdf(tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    assert "Page one line one." in extract_pdf(sample_pdf(tmp_path))


def test_asking_for_a_missing_pdftotext_says_how_to_get_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    with pytest.raises(MissingCommandError, match="poppler-utils"):
        extract_pdf(sample_pdf(tmp_path), backend="pdftotext")


def test_an_unknown_backend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="unknown pdf backend"):
        extract_pdf(sample_pdf(tmp_path), backend="magic")


class _Output:
    stdout = b"stub"


def test_markdown_blocks_keep_heading_levels() -> None:
    blocks = extract_module.markdown_blocks(
        "# Title\n\nIntro text.\n\n## Section\n\n- item one\n- item two\n"
    )
    assert [(b.heading, b.text) for b in blocks] == [
        (1, "Title"),
        (None, "Intro text."),
        (2, "Section"),
        (None, "item one"),
        (None, "item two"),
    ]


def test_a_setext_style_hash_suffix_is_dropped() -> None:
    blocks = extract_module.markdown_blocks("### Heading ###\n")
    assert [(b.heading, b.text) for b in blocks] == [(3, "Heading")]


def test_extract_blocks_wraps_plain_text_in_one_block(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("Line one.\n\nLine two.\n", encoding="utf-8")
    blocks = extract_module.extract_blocks(path)
    assert len(blocks) == 1
    assert blocks[0].heading is None
