"""Split plain text into the short lines that become subtitle lines.

One line is one TTS segment, so this also decides how the audio is
cut up.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 60

_JA_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_SENTENCE_END = re.compile(r"(?<=[。．！？!?])\s*")
# A '.' ends a sentence only when whitespace follows, so 3.14 stays whole.
_LATIN_END = re.compile(r"(?<=\.)\s+")
_PARAGRAPH = re.compile(r"\n\s*\n")
_INNER_NEWLINE = re.compile(r"\s*\n\s*")
# A chunk with no letters or digits (bullets, rules) is not worth speaking.
_SPEAKABLE = re.compile(r"\w")


def has_japanese(text: str) -> bool:
    """True when the text contains kana or kanji."""
    return _JA_CHARS.search(text) is not None


def split_sentences(text: str) -> list[str]:
    """Split one paragraph into sentences."""
    parts: list[str] = []
    for chunk in _SENTENCE_END.split(text):
        parts.extend(_LATIN_END.split(chunk))
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
