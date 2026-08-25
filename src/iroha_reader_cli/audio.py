"""Audio helpers built on the ffmpeg and ffprobe commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import CommandFailedError, MissingCommandError
from .proc import run

REQUIRED_COMMANDS = ("ffmpeg", "ffprobe")


def check_tools() -> None:
    """Fail early when ffmpeg or ffprobe is missing."""
    missing = [c for c in REQUIRED_COMMANDS if shutil.which(c) is None]
    if missing:
        raise MissingCommandError(
            f"missing commands: {', '.join(missing)}. "
            "Install ffmpeg first (Debian/Ubuntu: sudo apt install ffmpeg)."
        )


def _probe(path: str, entries: str, extra: Sequence[str] = ()) -> str:
    argv = ["ffprobe", "-v", "error", *extra,
            "-show_entries", entries,
            "-of", "default=noprint_wrappers=1:nokey=1", path]
    return run(argv).stdout.decode().strip()


def wav_duration(path: str) -> float | None:
    """Read the length straight out of a RIFF header, or None if it cannot.

    The local engines all write wav, and a long document is tens of
    thousands of segments: one ffprobe process each turns a minute of
    synthesis into several minutes of measuring.
    """
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(12)
            if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                return None
            byte_rate = 0
            while True:
                chunk = handle.read(8)
                if len(chunk) < 8:
                    return None
                name = chunk[:4]
                size = int.from_bytes(chunk[4:8], "little")
                if name == b"fmt ":
                    fmt = handle.read(size + size % 2)
                    if len(fmt) < 16:
                        return None
                    byte_rate = int.from_bytes(fmt[8:12], "little")
                elif name == b"data":
                    if byte_rate <= 0:
                        return None
                    # A streamed wav can claim a size it does not have.
                    actual = Path(path).stat().st_size - handle.tell()
                    return min(size, actual) / byte_rate
                else:
                    handle.seek(size + size % 2, 1)
    except OSError:
        return None


def duration_sec(path: str) -> float:
    """Return the audio length in seconds."""
    quick = wav_duration(path)
    if quick is not None:
        return quick
    out = _probe(path, "format=duration")
    try:
        return float(out)
    except ValueError as err:
        raise CommandFailedError(
            ["ffprobe", path],
            subprocess.CalledProcessError(1, "ffprobe", stderr=b"no duration in the output"),
        ) from err


def sample_rate(path: str) -> int:
    """Return the sample rate of the first audio stream."""
    return int(_probe(path, "stream=sample_rate", ("-select_streams", "a:0")))


def make_silence(path: str, ms: int, rate: int) -> None:
    """Write a short silence file that matches the segment sample rate."""
    run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=mono",
        "-t", f"{ms / 1000:.3f}",
        path,
    ])


@dataclass(frozen=True, slots=True)
class ChapterMark:
    """One chapter of the finished audio file."""

    title: str
    start: float
    end: float


def _ffmetadata(chapters: Sequence[ChapterMark], title: str = "") -> str:
    """Render chapters in ffmpeg's metadata format."""

    def escape(text: str) -> str:
        # = ; # and \ are the special characters of this format.
        for mark in ("\\", "=", ";", "#", "\n"):
            text = text.replace(mark, "\\" + mark)
        return text

    out = [";FFMETADATA1"]
    if title:
        out.append(f"title={escape(title)}")
    for chapter in chapters:
        out += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={max(0, round(chapter.start * 1000))}",
            f"END={max(0, round(chapter.end * 1000))}",
            f"title={escape(chapter.title)}",
        ]
    return "\n".join(out) + "\n"


def write_chapters(path: str, chapters: Sequence[ChapterMark],
                   title: str = "") -> None:
    """Write chapter marks into an existing audio file, in place."""
    target = Path(path)
    meta = target.with_suffix(target.suffix + ".ffmeta")
    staged = target.with_suffix(target.suffix + ".chapters" + target.suffix)
    try:
        meta.write_text(_ffmetadata(chapters, title), encoding="utf-8")
        run([
            "ffmpeg", "-y", "-v", "error",
            "-i", str(target), "-i", str(meta),
            "-map_metadata", "1", "-map", "0:a", "-codec", "copy",
            str(staged),
        ])
        staged.replace(target)
    finally:
        meta.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)


def concat(paths: Sequence[str], out_path: str,
           bitrate: str = "64k", loudnorm: bool = False) -> None:
    """Join segment files into one audio file."""
    if not paths:
        raise ValueError("concat needs at least one input file")
    fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="iroha_concat_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for p in paths:
                # The concat demuxer quotes with '' and escapes ' as '\''.
                escaped = str(Path(p).resolve()).replace("'", r"'\''")
                f.write(f"file '{escaped}'\n")
        argv = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
        ]
        argv += ["-ac", "1"]
        if loudnorm:
            # A two-pass measure would be more exact. One pass is enough here.
            argv += ["-af", "loudnorm"]
        if out_path.lower().endswith(".mp3"):
            argv += ["-b:a", bitrate]
        argv.append(out_path)
        run(argv)
    finally:
        Path(list_path).unlink(missing_ok=True)
