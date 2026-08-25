"""Build SRT and VTT subtitle text from lines, starts, and durations."""


def _clock(sec: float, ms_sep: str) -> str:
    """Format seconds as hh:mm:ss with a millisecond part."""
    if sec < 0:
        sec = 0.0
    ms = round(sec * 1000)
    hh, rest = divmod(ms, 3600_000)
    mm, rest = divmod(rest, 60_000)
    ss, mmm = divmod(rest, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d}{ms_sep}{mmm:03d}"


def build_srt(lines: list[str], starts: list[float], durations: list[float]) -> str:
    """Return the full SRT file content."""
    out: list[str] = []
    for i, (text, start, dur) in enumerate(zip(lines, starts, durations), start=1):
        end = start + dur
        out.append(str(i))
        out.append(f"{_clock(start, ',')} --> {_clock(end, ',')}")
        out.append(text)
        out.append("")
    return "\n".join(out) + "\n"


def build_vtt(lines: list[str], starts: list[float], durations: list[float]) -> str:
    """Return the full WebVTT file content."""
    out: list[str] = ["WEBVTT", ""]
    for text, start, dur in zip(lines, starts, durations):
        end = start + dur
        out.append(f"{_clock(start, '.')} --> {_clock(end, '.')}")
        out.append(text)
        out.append("")
    return "\n".join(out) + "\n"
