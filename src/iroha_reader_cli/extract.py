"""Extract plain text from md, pdf, and txt files."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import epub
from .document import Block
from .errors import MissingCommandError, ReaderError, UnsupportedInputError
from .proc import run

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_TABLE_SEP = re.compile(r"^\s*\|[-:\s|]+\|\s*$", re.M)

MARKDOWN_SUFFIXES = (".md", ".markdown")
TEXT_SUFFIXES = (".txt", ".text")
SUPPORTED_SUFFIXES = (*MARKDOWN_SUFFIXES, ".pdf", ".epub", *TEXT_SUFFIXES)


def read_text_file(path: Path) -> str:
    """Read a text file. utf-8 first, then cp932 for older Japanese files."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Last resort: keep going with replacement characters.
    return data.decode("utf-8", errors="replace")


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+")
_RULE = re.compile(r"^\s*[-*_]{3,}\s*$")
_QUOTE = re.compile(r"^\s*>\s?")


def _clean_inline(text: str) -> str:
    """Strip the markup that lives inside a line."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)   # images -> alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)    # links -> label
    text = text.replace("|", " ")                           # table pipes
    text = re.sub(r"`([^`]*)`", r"\1", text)                # inline code
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.S)  # bold
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)           # italic (star only)
    text = re.sub(r"<[^>]+>", "", text)                     # html tags
    return text.strip()


def markdown_blocks(text: str, keep_code: bool = False) -> list[Block]:
    """Split markdown into paragraphs, remembering which ones are headings.

    Headings and list items each become their own block, so each one
    lands on its own subtitle line.
    """
    if keep_code:
        # Keep the code lines, drop only the fence markers.
        text = re.sub(r"^```[^\n]*$", "", text, flags=re.M)
    else:
        # Drop whole code blocks. Code is noise when spoken.
        text = _CODE_FENCE.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)   # html comments
    text = _TABLE_SEP.sub("", text)                      # table separator rows

    blocks: list[Block] = []
    buffer: list[str] = []

    def flush() -> None:
        joined = _clean_inline(" ".join(part.strip() for part in buffer)).strip()
        buffer.clear()
        if joined:
            blocks.append(Block(joined))

    for raw in text.splitlines():
        line = _QUOTE.sub("", raw)
        heading = _HEADING.match(line)
        if heading:
            flush()
            title = _clean_inline(heading.group(2))
            if title:
                blocks.append(Block(title, heading=len(heading.group(1))))
            continue
        if not line.strip() or _RULE.match(line):
            flush()
            continue
        if _LIST_ITEM.match(line):
            flush()
            line = _LIST_ITEM.sub("", line)
        buffer.append(line)
    flush()
    return blocks


def strip_markdown(text: str, keep_code: bool = False) -> str:
    """Remove markdown syntax and keep the readable text."""
    return "\n\n".join(block.text for block in markdown_blocks(text, keep_code))


PDF_BACKENDS = ("auto", "pdftotext", "pypdf")
PDFTOTEXT = "pdftotext"


def _pdf_with_pypdf(path: Path, pages: tuple[int, int | None] | None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as err:  # pragma: no cover - dependency is required
        raise ReaderError("pdf input needs the pypdf package: pip install pypdf") from err

    reader = PdfReader(str(path))
    selected = reader.pages
    if pages is not None:
        start, end = pages
        if start > len(reader.pages):
            raise ReaderError(
                f"page {start} is past the end of {path.name} "
                f"({len(reader.pages)} pages)"
            )
        selected = reader.pages[start - 1:end]
    return "\n".join(page.extract_text() or "" for page in selected)


def _pdf_with_pdftotext(path: Path, pages: tuple[int, int | None] | None) -> str:
    argv = [PDFTOTEXT]
    if pages is not None:
        start, end = pages
        argv += ["-f", str(start)]
        if end is not None:
            argv += ["-l", str(end)]
    # No -layout on purpose: the default mode undoes columns and gives
    # reading order, which is what a listener needs.
    argv += [str(path), "-"]
    return run(argv).stdout.decode("utf-8", "replace")


def extract_pdf(path: Path, pages: tuple[int, int | None] | None = None,
                backend: str = "auto") -> str:
    """Extract text from a pdf.

    `pages` is a 1-based (start, end) range. An end of None means the
    last page. `backend` is auto, pdftotext, or pypdf; auto prefers
    pdftotext when poppler is installed, because it reads multi-column
    pages in the right order.
    """
    if backend not in PDF_BACKENDS:
        raise ReaderError(f"unknown pdf backend: {backend} "
                          f"(use {' / '.join(PDF_BACKENDS)})")
    if backend == "auto":
        backend = PDFTOTEXT if shutil.which(PDFTOTEXT) else "pypdf"
    if backend == PDFTOTEXT:
        if shutil.which(PDFTOTEXT) is None:
            raise MissingCommandError(
                "pdftotext is missing. Install poppler-utils "
                "(Debian/Ubuntu: sudo apt install poppler-utils), "
                "or use --pdf-backend pypdf."
            )
        return _pdf_with_pdftotext(path, pages)
    return _pdf_with_pypdf(path, pages)


def parse_page_range(spec: str) -> tuple[int, int | None]:
    """Parse a page range like 3-10, 5, or 3-."""
    text = spec.strip()
    try:
        if "-" in text:
            first, _, last = text.partition("-")
            start = int(first)
            end = int(last) if last.strip() else None
        else:
            start = end = int(text)
        if start < 1 or (end is not None and end < start):
            raise ValueError
    except ValueError:
        raise ReaderError(f"bad page range: {spec} (use 3-10, 5, or 3-)") from None
    return start, end


#: What --type accepts for stdin, mapped to the suffix used internally.
INPUT_TYPES = ("md", "txt", "pdf", "epub")


def extract_blocks(path: Path, keep_code: bool = False,
                   pages: tuple[int, int | None] | None = None,
                   pdf_backend: str = "auto") -> list[Block]:
    """Extract a document as blocks, keeping markdown heading levels.

    Formats that carry no structure of their own come back as one block.
    """
    suffix = path.suffix.lower()
    if suffix in (*MARKDOWN_SUFFIXES, ".epub") and not path.exists():
        raise ReaderError(f"file not found: {path}")
    if suffix in MARKDOWN_SUFFIXES:
        return markdown_blocks(read_text_file(path), keep_code=keep_code)
    if suffix == ".epub":
        return epub.extract_blocks(path)
    return [Block(extract(path, keep_code=keep_code, pages=pages,
                          pdf_backend=pdf_backend))]


def extract(path: Path, keep_code: bool = False,
            pages: tuple[int, int | None] | None = None,
            pdf_backend: str = "auto") -> str:
    """Extract plain text, picking the reader from the file suffix."""
    if not path.exists():
        raise ReaderError(f"file not found: {path}")
    if path.is_dir():
        raise ReaderError(f"not a file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path, pages=pages, backend=pdf_backend)
    if suffix in MARKDOWN_SUFFIXES:
        return strip_markdown(read_text_file(path), keep_code=keep_code)
    if suffix in TEXT_SUFFIXES:
        return read_text_file(path)
    if suffix == ".epub":
        # epub is structured; go through extract_blocks to keep its headings.
        return "\n\n".join(block.text for block in epub.extract_blocks(path))
    raise UnsupportedInputError(
        f"unsupported file type: {suffix or path.name} "
        f"(use {' / '.join(SUPPORTED_SUFFIXES)})"
    )
