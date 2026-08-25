"""Audio helpers. Uses ffmpeg and ffprobe as subprocesses."""

import os
import subprocess
import tempfile


def duration_sec(path: str) -> float:
    """Return the audio length in seconds."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())


def sample_rate(path: str) -> int:
    """Return the sample rate of the first audio stream."""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(out.stdout.strip())


def make_silence(path: str, ms: int, rate: int) -> None:
    """Write a short silence file. Match the segment sample rate."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi",
            "-i", f"anullsrc=r={rate}:cl=mono",
            "-t", f"{ms / 1000:.3f}",
            path,
        ],
        check=True,
    )


def concat(paths: list[str], out_path: str,
           bitrate: str = "64k", loudnorm: bool = False) -> None:
    """Join segment files into one audio file."""
    fd, list_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for p in paths:
                # Paths are made by this tool. They hold no quotes.
                f.write(f"file '{os.path.abspath(p)}'\n")
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-ac", "1",
        ]
        if loudnorm:
            # Two-pass would be more exact. One pass is fine here.
            cmd += ["-af", "loudnorm"]
        if out_path.lower().endswith(".mp3"):
            cmd += ["-b:a", bitrate]
        cmd.append(out_path)
        subprocess.run(cmd, check=True)
    finally:
        os.unlink(list_path)
