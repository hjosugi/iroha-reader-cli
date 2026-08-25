"""Split plain text into the short lines that become subtitle lines.

One line is one TTS segment, so this also decides how the audio is
cut up.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .document import Block, Line

DEFAULT_MAX_CHARS = 60

_JA_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
#: Closing quotes and brackets that belong to the sentence before them.
_CLOSERS = "」』）\u201d\u2019\"'"
#: Split after a sentence ender, or after the closer that follows it, so
#: 「こんにちは。」 stays in one piece.
_SENTENCE_END = re.compile(
    rf"(?<=[。．！？!?][{_CLOSERS}])\s*"
    rf"|(?<=[。．！？!?])(?![{_CLOSERS}])\s*"
)
# A '.' ends a sentence only when whitespace follows, so 3.14 stays whole.
# The closer may sit between the two: `he said "stop." Then...`.
_LATIN_END = re.compile(
    rf"(?<=\.)(?![{_CLOSERS}])\s+"
    rf"|(?<=\.[{_CLOSERS}])\s+"
)
#: Words that end in a full stop without ending the sentence.
_ABBREVIATION_WORDS = (
    # titles
    "mr mrs ms dr prof sr jr st rev hon gen col sgt lt capt "
    # latin and shorthand
    "vs etc e.g i.e cf al ca approx "
    # references
    "fig figs no nos vol vols pp ed eds ch chap sec "
    # organisations
    "inc ltd co corp dept est univ "
    # months and days
    "jan feb mar apr jun jul aug sept sep oct nov dec "
    "mon tue tues wed thu thur thurs fri sat sun"
)
ABBREVIATIONS = frozenset(_ABBREVIATION_WORDS.split())
_LAST_WORD = re.compile(r"([\w.]+)\.$")
_PARAGRAPH = re.compile(r"\n\s*\n")
_INNER_NEWLINE = re.compile(r"\s*\n\s*")
# A chunk with no letters or digits (bullets, rules) is not worth speaking.
_SPEAKABLE = re.compile(r"\w")


#: A document with at least this much kana and kanji is read as Japanese.
JAPANESE_SHARE = 0.1
_WORD_CHARS = re.compile(r"\w")


def has_japanese(text: str) -> bool:
    """True when the text contains any kana or kanji."""
    return _JA_CHARS.search(text) is not None


def japanese_share(text: str) -> float:
    """How much of the text is kana or kanji, from 0 to 1."""
    letters = len(_WORD_CHARS.findall(text))
    if not letters:
        return 0.0
    return len(_JA_CHARS.findall(text)) / letters


def is_japanese(text: str, threshold: float = JAPANESE_SHARE) -> bool:
    """True when a Japanese voice is the right one for this text.

    One Japanese word quoted in an English page is not a reason to
    read the whole page with a Japanese engine, so this asks how much
    of it is Japanese rather than whether any of it is.
    """
    return japanese_share(text) >= threshold


def _ends_mid_sentence(chunk: str) -> bool:
    """True when a chunk ends in a full stop that is not a full stop.

    `Dr.`, `e.g.`, and the `J.` of `J. R. R. Tolkien` all look like
    sentence ends to a regular expression.
    """
    match = _LAST_WORD.search(chunk.rstrip())
    if match is None:
        return False
    word = match.group(1).lower().rstrip(".")
    return len(word) == 1 or word in ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    """Split one paragraph into sentences."""
    parts: list[str] = []
    for chunk in _SENTENCE_END.split(text):
        for piece in _LATIN_END.split(chunk):
            # A lower case start, or an abbreviation before it, means the
            # sentence did not actually end there.
            if parts and (_ends_mid_sentence(parts[-1])
                          or (piece[:1].islower() and parts[-1].endswith("."))):
                parts[-1] = f"{parts[-1].rstrip()} {piece.lstrip()}"
            else:
                parts.append(piece)
    return [part.strip() for part in parts if part.strip()]


def wrap(line: str, max_chars: int) -> list[str]:
    """Cut one long sentence into chunks of max_chars or less."""
    if len(line) <= max_chars:
        return [line]
    chunks: list[str] = []
    rest = line
    while len(rest) > max_chars:
        window = rest[:max_chars]
        # Prefer a natural break: a Japanese comma, then a latin comma, then a space.
        pos = max(window.rfind("、"), window.rfind(", "), window.rfind(" "))
        pos = max_chars if pos <= 0 else pos + 1
        chunks.append(rest[:pos].strip())
        rest = rest[pos:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def segment_blocks(blocks: Sequence[Block],
                   max_chars: int = DEFAULT_MAX_CHARS) -> list[Line]:
    """Cut every block into subtitle lines, keeping the heading levels.

    Only the first line of a heading stays marked: a heading that wraps
    is still one heading.
    """
    lines: list[Line] = []
    for block in blocks:
        for index, chunk in enumerate(segment(block.text, max_chars)):
            lines.append(Line(chunk, block.heading if index == 0 else None))
    return lines


def segment(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Turn raw text into clean short lines."""
    if max_chars < 1:
        raise ValueError("max_chars must be 1 or more")
    lines: list[str] = []
    for block in _PARAGRAPH.split(text):
        # Join the wrapped source lines of one paragraph into a single string.
        flat = _INNER_NEWLINE.sub(" ", block).strip()
        if not flat:
            continue
        for sentence in split_sentences(flat):
            lines.extend(chunk for chunk in wrap(sentence, max_chars)
                         if _SPEAKABLE.search(chunk))
    return lines
