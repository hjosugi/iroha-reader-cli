"""Read an epub as blocks.

An epub is a zip of XHTML with a spine that gives the reading order.
That is all this needs: the spine for the order, the headings for the
chapters, and the text for everything else. No third party library.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from .document import Block
from .errors import ReaderError

CONTAINER = "META-INF/container.xml"
XHTML_TYPES = ("application/xhtml+xml", "text/html")

#: Tags that end the current block of text.
_BLOCK_TAGS = {
    "p", "div", "li", "blockquote", "pre", "section", "article",
    "td", "th", "tr", "figcaption", "dd", "dt", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_HEADINGS = {f"h{level}": level for level in range(1, 7)}
_SKIP_TAGS = {"script", "style", "head", "title", "svg"}
_WS = re.compile(r"\s+")


class _Blocks(HTMLParser):
    """Collects the readable text of one XHTML document, block by block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._buffer: list[str] = []
        self._heading: int | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if tag == "br":
            self._buffer.append(" ")
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            self._heading = _HEADINGS.get(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = _WS.sub(" ", "".join(self._buffer)).strip()
        heading, self._heading = self._heading, None
        self._buffer.clear()
        if text:
            self.blocks.append(Block(text, heading=heading))


def html_blocks(html: str) -> list[Block]:
    """Turn one XHTML document into blocks."""
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    return parser.blocks


def _text_of(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("utf-8", "replace")


def _tag(element: ElementTree.Element) -> str:
    """The tag without its namespace."""
    return element.tag.rsplit("}", 1)[-1]


def _opf_path(archive: zipfile.ZipFile) -> str:
    try:
        root = ElementTree.fromstring(_text_of(archive, CONTAINER))
    except (KeyError, ElementTree.ParseError) as err:
        raise ReaderError("this does not look like an epub: no container.xml") from err
    for element in root.iter():
        if _tag(element) == "rootfile":
            full = element.get("full-path")
            if full:
                return full
    raise ReaderError("this epub names no package file in container.xml")


def spine_documents(archive: zipfile.ZipFile) -> list[str]:
    """Return the XHTML entries of the archive, in reading order."""
    opf = _opf_path(archive)
    base = posixpath.dirname(opf)
    try:
        package = ElementTree.fromstring(_text_of(archive, opf))
    except (KeyError, ElementTree.ParseError) as err:
        raise ReaderError(f"cannot read the epub package file: {opf}") from err

    manifest: dict[str, tuple[str, str]] = {}
    order: list[str] = []
    for element in package.iter():
        name = _tag(element)
        if name == "item":
            item_id = element.get("id")
            href = element.get("href")
            if item_id and href:
                manifest[item_id] = (href, element.get("media-type", ""))
        elif name == "itemref":
            ref = element.get("idref")
            if ref:
                order.append(ref)

    documents: list[str] = []
    for ref in order:
        href, media_type = manifest.get(ref, ("", ""))
        if not href or (media_type and media_type not in XHTML_TYPES):
            continue
        path = posixpath.normpath(posixpath.join(base, href.split("#", 1)[0]))
        if path in archive.namelist():
            documents.append(path)
    return documents


def extract_blocks(path: Path) -> list[Block]:
    """Read an epub in reading order, keeping its headings."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as err:
        raise ReaderError(f"cannot open {path.name} as an epub: {err}") from err
    with archive:
        documents = spine_documents(archive)
        if not documents:
            raise ReaderError(f"no readable chapters in {path.name}")
        blocks: list[Block] = []
        for name in documents:
            blocks.extend(html_blocks(_text_of(archive, name)))
    return blocks
