"""Split plain text into short lines for LRC and TTS."""

import re

_JA_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def has_japanese(text: str) -> bool:
    """Return True when the text contains Japanese characters."""
    return _JA_CHARS.search(text) is not None


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Split after Japanese sentence enders.
    parts = re.split(r"(?<=[。．！？!?])\s*", text)
    out: list[str] = []
    for part in parts:
        # Split after '.' only when a space or end follows.
        # This keeps numbers like 3.14 together.
        out.extend(re.split(r"(?<=\.)\s+", part))
    return [s.strip() for s in out if s.strip()]


def _wrap(line: str, max_chars: int) -> list[str]:
    """Wrap one long line into chunks of max_chars or less."""
    if len(line) <= max_chars:
        return [line]
    chunks: list[str] = []
    rest = line
    while len(rest) > max_chars:
        window = rest[:max_chars]
        # Prefer a natural break point.
        pos = max(window.rfind("、"), window.rfind(", "), window.rfind(" "))
        if pos <= 0:
            pos = max_chars
        else:
            pos += 1
        chunks.append(rest[:pos].strip())
        rest = rest[pos:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def segment(text: str, max_chars: int = 60) -> list[str]:
    """Turn raw text into a list of clean short lines."""
    lines: list[str] = []
    # Paragraphs are split by blank lines.
    for block in re.split(r"\n\s*\n", text):
        # Join wrapped source lines into one string.
        flat = re.sub(r"\s*\n\s*", " ", block).strip()
        if not flat:
            continue
        for sentence in _split_sentences(flat):
            lines.extend(_wrap(sentence, max_chars))
    return lines
