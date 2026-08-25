"""Turn measured segment lengths into subtitle timestamps.

Line N starts after every earlier segment plus one gap each, which is
exactly how the segments are joined, so the timing cannot drift.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Word:
    """One spoken word. Relative to its line until the timeline shifts it."""

    text: str
    start: float
    duration: float


@dataclass(frozen=True, slots=True)
class Timeline:
    """Start time of every line, plus the total length."""

    starts: tuple[float, ...]
    durations: tuple[float, ...]
    total: float
    #: Per line, in absolute time. None unless the engine reports words.
    words: tuple[tuple[Word, ...], ...] | None = None


def build(durations: Sequence[float], gap_sec: float,
          words: Sequence[Sequence[Word]] | None = None) -> Timeline:
    """Lay the measured segments out on one timeline.

    `words` are timed against the start of their own line; they come
    back timed against the start of the file.
    """
    if gap_sec < 0:
        raise ValueError("gap_sec must be 0 or more")
    starts: list[float] = []
    cursor = 0.0
    for duration in durations:
        starts.append(cursor)
        cursor += duration + gap_sec
    total = cursor - gap_sec if durations else 0.0

    shifted: tuple[tuple[Word, ...], ...] | None = None
    if words is not None:
        shifted = tuple(
            tuple(Word(word.text, start + word.start, word.duration)
                  for word in line)
            for start, line in zip(starts, words, strict=False)
        )
    return Timeline(tuple(starts), tuple(durations), total, shifted)
