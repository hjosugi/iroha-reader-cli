"""Render the timed lines as LRC, SRT, or WebVTT.

LRC carries a start time per line, which is what music players use to
highlight the current line. SRT and VTT also need an end time, which
is the start plus the measured length of that segment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .timeline import Timeline

FORMATS = ("lrc", "srt", "vtt")
DEFAULT_FORMATS = ("lrc",)


def _lrc_stamp(sec: float) -> str:
    """Format seconds as [mm:ss.xx]."""
    sec = max(sec, 0.0)
    minutes = int(sec // 60)
    return f"[{minutes:02d}:{sec - minutes * 60:05.2f}]"


def _clock(sec: float, ms_sep: str) -> str:
    """Format seconds as hh:mm:ss with a millisecond part."""
    ms = round(max(sec, 0.0) * 1000)
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{ms_sep}{millis:03d}"


def build_lrc(lines: Sequence[str], timeline: Timeline, title: str = "") -> str:
    """Return a full LRC file."""
    out = [
        f"[ti:{title}]",
        "[re:iroha-reader-cli]",
        f"[length:{_lrc_stamp(timeline.total)[1:-1]}]",
        "",
    ]
    out += [f"{_lrc_stamp(start)}{text}"
            for text, start in zip(lines, timeline.starts, strict=False)]
    return "\n".join(out) + "\n"


def build_srt(lines: Sequence[str], timeline: Timeline, _title: str = "") -> str:
    """Return a full SRT file. SRT has no title field, so the title is ignored."""
    out: list[str] = []
    cues = zip(lines, timeline.starts, timeline.durations, strict=False)
    for index, (text, start, duration) in enumerate(cues, start=1):
        out += [
            str(index),
            f"{_clock(start, ',')} --> {_clock(start + duration, ',')}",
            text,
            "",
        ]
    return "\n".join(out) + "\n"


def build_vtt(lines: Sequence[str], timeline: Timeline, _title: str = "") -> str:
    """Return a full WebVTT file. VTT has no title field, so the title is ignored."""
    out: list[str] = ["WEBVTT", ""]
    cues = zip(lines, timeline.starts, timeline.durations, strict=False)
    for text, start, duration in cues:
        out += [
            f"{_clock(start, '.')} --> {_clock(start + duration, '.')}",
            text,
            "",
        ]
    return "\n".join(out) + "\n"


_BUILDERS: dict[str, Callable[[Sequence[str], Timeline, str], str]] = {
    "lrc": build_lrc,
    "srt": build_srt,
    "vtt": build_vtt,
}


def render(fmt: str, lines: Sequence[str], timeline: Timeline, title: str = "") -> str:
    """Render one subtitle format by name."""
    try:
        builder = _BUILDERS[fmt]
    except KeyError:
        raise ValueError(f"unknown subtitle format: {fmt}") from None
    return builder(lines, timeline, title)
