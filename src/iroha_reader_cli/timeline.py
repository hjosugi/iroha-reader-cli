"""Turn measured segment lengths into subtitle timestamps.

Line N starts after every earlier segment plus one gap each, which is
exactly how the segments are joined, so the timing cannot drift.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Timeline:
    """Start time of every line, plus the total length."""

    starts: tuple[float, ...]
    durations: tuple[float, ...]
    total: float


def build(durations: Sequence[float], gap_sec: float) -> Timeline:
    """Lay the measured segments out on one timeline."""
    if gap_sec < 0:
        raise ValueError("gap_sec must be 0 or more")
    starts: list[float] = []
    cursor = 0.0
    for duration in durations:
        starts.append(cursor)
        cursor += duration + gap_sec
    total = cursor - gap_sec if durations else 0.0
    return Timeline(tuple(starts), tuple(durations), total)
