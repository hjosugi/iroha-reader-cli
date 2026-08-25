"""Audio helpers built on the ffmpeg and ffprobe commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
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


def duration_sec(path: str) -> float:
    """Return the audio length in seconds."""
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
            "-ac", "1",
        ]
        if loudnorm:
            # A two-pass measure would be more exact. One pass is enough here.
            argv += ["-af", "loudnorm"]
        if out_path.lower().endswith(".mp3"):
            argv += ["-b:a", bitrate]
        argv.append(out_path)
        run(argv)
    finally:
        Path(list_path).unlink()
