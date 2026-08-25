"""The shape of a document between extraction and synthesis.

Markdown knows which lines are headings; plain text and pdf do not.
Keeping that one fact all the way through is what makes chapters
possible.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: A file name safe form of a chapter title.
_SLUG_STRIP = re.compile(r"[^\w\-]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class Block:
    """One paragraph or heading, before it is cut into subtitle lines."""

    text: str
    heading: int | None = None


@dataclass(frozen=True, slots=True)
class Line:
    """One subtitle line. `heading` is set on the first line of a heading."""

    text: str
    heading: int | None = None


@dataclass(frozen=True, slots=True)
class Chapter:
    """A run of lines that starts at a heading."""

    title: str
    lines: tuple[Line, ...]
    #: Index of the first line in the whole document.
    start: int

    @property
    def stop(self) -> int:
        return self.start + len(self.lines)


def texts(lines: Sequence[Line]) -> list[str]:
    return [line.text for line in lines]


def chapters(lines: Sequence[Line], level: int, title: str = "") -> list[Chapter]:
    """Split lines at every heading of `level` or shallower.

    Lines before the first heading become an opening chapter, so the
    parts always cover the whole document.
    """
    starts = [index for index, line in enumerate(lines)
              if line.heading is not None and line.heading <= level]
    if not starts:
        return [Chapter(title, tuple(lines), 0)] if lines else []
    if starts[0] != 0:
        starts.insert(0, 0)

    out: list[Chapter] = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(lines)
        chunk = tuple(lines[start:stop])
        if not chunk:
            continue
        head = chunk[0].text if chunk[0].heading is not None else title
        out.append(Chapter(head, chunk, start))
    return out


def slug(text: str, fallback: str = "part") -> str:
    """A short, file name safe version of a chapter title."""
    cleaned = _SLUG_STRIP.sub("-", text.strip()).strip("-")
    return (cleaned[:40].rstrip("-") or fallback)
