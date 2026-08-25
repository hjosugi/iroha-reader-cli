"""Extract plain text from md, pdf, and txt files."""

import re
from pathlib import Path

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_TABLE_SEP = re.compile(r"^\s*\|[-:\s|]+\|\s*$", re.M)


def read_text_file(path: Path) -> str:
    """Read a text file. Try utf-8 first, then cp932."""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    # Last resort. Replace bad bytes.
    return data.decode("utf-8", errors="replace")


def strip_markdown(text: str, keep_code: bool = False) -> str:
    """Remove markdown syntax. Keep readable text only."""
    if keep_code:
        # Keep code lines. Drop only the fence markers.
        text = re.sub(r"^```[^\n]*$", "", text, flags=re.M)
    else:
        # Drop whole code blocks. Code is noise when spoken.
        text = _CODE_FENCE.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)          # html comments
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)       # images -> alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)        # links -> label
    # Headings and list items become their own paragraphs.
    # This keeps each one on its own LRC line.
    text = re.sub(r"^#{1,6}\s*(.+)$", r"\n\1\n", text, flags=re.M)      # headings
    text = re.sub(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", "\n", text, flags=re.M)  # list markers
    text = re.sub(r"^>\s?", "", text, flags=re.M)               # blockquotes
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.M)      # horizontal rules
    text = _TABLE_SEP.sub("", text)                             # table separator rows
    text = text.replace("|", " ")                               # table pipes
    text = re.sub(r"`([^`]*)`", r"\1", text)                    # inline code
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.S)  # bold
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)                # italic (star only)
    text = re.sub(r"<[^>]+>", "", text)                         # html tags
    return text


def extract_pdf(path: Path, pages: tuple[int, int | None] | None = None) -> str:
    """Extract text from a pdf with pypdf.

    pages is a 1-based (start, end) range. end None means the last page.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    selected = reader.pages
    if pages is not None:
        start, end = pages
        if start > len(reader.pages):
            raise ValueError(
                f"page {start} is past the end ({len(reader.pages)} pages)")
        selected = reader.pages[start - 1:end]
    out = []
    for page in selected:
        out.append(page.extract_text() or "")
    return "\n".join(out)


def extract(path: Path, keep_code: bool = False,
            pages: tuple[int, int | None] | None = None) -> str:
    """Extract plain text based on the file suffix."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path, pages=pages)
    if suffix in (".md", ".markdown"):
        return strip_markdown(read_text_file(path), keep_code=keep_code)
    if suffix == ".txt":
        return read_text_file(path)
    raise ValueError(f"unsupported file type: {suffix} (use .md / .pdf / .txt)")
