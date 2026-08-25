"""Extract plain text from md, pdf, and txt files."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import ReaderError, UnsupportedInputError

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_TABLE_SEP = re.compile(r"^\s*\|[-:\s|]+\|\s*$", re.M)

MARKDOWN_SUFFIXES = (".md", ".markdown")
TEXT_SUFFIXES = (".txt", ".text")
SUPPORTED_SUFFIXES = (*MARKDOWN_SUFFIXES, ".pdf", *TEXT_SUFFIXES)


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


def strip_markdown(text: str, keep_code: bool = False) -> str:
    """Remove markdown syntax and keep the readable text."""
    if keep_code:
        # Keep the code lines, drop only the fence markers.
        text = re.sub(r"^```[^\n]*$", "", text, flags=re.M)
    else:
        # Drop whole code blocks. Code is noise when spoken.
        text = _CODE_FENCE.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)           # html comments
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)        # images -> alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)         # links -> label
    # Headings and list items become their own paragraphs so that each
    # one lands on its own subtitle line.
    text = re.sub(r"^#{1,6}\s*(.+)$", r"\n\1\n", text, flags=re.M)
    text = re.sub(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", "\n", text, flags=re.M)
    text = re.sub(r"^>\s?", "", text, flags=re.M)                # blockquotes
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.M)       # horizontal rules
    text = _TABLE_SEP.sub("", text)                              # table separators
    text = text.replace("|", " ")                                # table pipes
    text = re.sub(r"`([^`]*)`", r"\1", text)                     # inline code
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.S)  # bold
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)                 # italic (star only)
    text = re.sub(r"<[^>]+>", "", text)                          # html tags
    return text


def extract_pdf(path: Path, pages: tuple[int, int | None] | None = None) -> str:
    """Extract text from a pdf with pypdf.

    `pages` is a 1-based (start, end) range. An end of None means the
    last page.
    """
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
INPUT_TYPES = ("md", "txt", "pdf")


def extract(path: Path, keep_code: bool = False,
            pages: tuple[int, int | None] | None = None) -> str:
    """Extract plain text, picking the reader from the file suffix."""
    if not path.exists():
        raise ReaderError(f"file not found: {path}")
    if path.is_dir():
        raise ReaderError(f"not a file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path, pages=pages)
    if suffix in MARKDOWN_SUFFIXES:
        return strip_markdown(read_text_file(path), keep_code=keep_code)
    if suffix in TEXT_SUFFIXES:
        return read_text_file(path)
    raise UnsupportedInputError(
        f"unsupported file type: {suffix or path.name} "
        f"(use {' / '.join(SUPPORTED_SUFFIXES)})"
    )
