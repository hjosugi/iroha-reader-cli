"""Render the timed lines as LRC, SRT, or WebVTT.

LRC carries a start time per line, which is what music players use to
highlight the current line. SRT and VTT also need an end time, which
is the start plus the measured length of that segment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .timeline import Timeline, Word

FORMATS = ("lrc", "srt", "vtt")
DEFAULT_FORMATS = ("lrc",)


def _mmss(sec: float) -> str:
    """Format seconds as mm:ss.xx."""
    sec = max(sec, 0.0)
    minutes = int(sec // 60)
    return f"{minutes:02d}:{sec - minutes * 60:05.2f}"


def _lrc_stamp(sec: float) -> str:
    """Format seconds as [mm:ss.xx]."""
    return f"[{_mmss(sec)}]"


def _tag_words(line: str, words: Sequence[Word], stamp: Callable[[float], str]) -> str:
    """Put a timestamp in front of every word, keeping the line intact.

    The engine reports words without their punctuation, so the tags are
    threaded into the original text instead of rebuilt from the word
    list. A word that cannot be found is left untagged rather than
    guessed at.
    """
    out: list[str] = []
    cursor = 0
    for word in words:
        found = line.find(word.text, cursor)
        if found < 0:
            found = line.lower().find(word.text.lower(), cursor)
        if found < 0:
            continue
        out.append(line[cursor:found])
        out.append(stamp(word.start))
        out.append(line[found:found + len(word.text)])
        cursor = found + len(word.text)
    out.append(line[cursor:])
    return "".join(out)


def _clock(sec: float, ms_sep: str) -> str:
    """Format seconds as hh:mm:ss with a millisecond part."""
    ms = round(max(sec, 0.0) * 1000)
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{ms_sep}{millis:03d}"


def build_lrc(lines: Sequence[str], timeline: Timeline, title: str = "") -> str:
    """Return a full LRC file.

    When the timeline carries word times, every word gets its own
    <mm:ss.xx> tag as well, which is what karaoke players read as
    Enhanced LRC.
    """
    out = [
        f"[ti:{title}]",
        "[re:iroha-reader-cli]",
        f"[length:{_mmss(timeline.total)}]",
        "",
    ]
    for index, (text, start) in enumerate(zip(lines, timeline.starts, strict=False)):
        words = timeline.words[index] if timeline.words is not None else ()
        body = _tag_words(text, words, lambda sec: f"<{_mmss(sec)}>") if words else text
        out.append(f"{_lrc_stamp(start)}{body}")
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
    for index, (text, start, duration) in enumerate(cues):
        words = timeline.words[index] if timeline.words is not None else ()
        # WebVTT reads the same inline timestamps as karaoke cues.
        body = (_tag_words(text, words, lambda sec: f"<{_clock(sec, '.')}>")
                if words else text)
        out += [
            f"{_clock(start, '.')} --> {_clock(start + duration, '.')}",
            body,
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
