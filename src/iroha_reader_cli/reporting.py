"""Progress and status output.

Everything goes to stderr so that stdout stays clean for piping
(`--dry-run` writes the lines themselves to stdout).
"""

from __future__ import annotations

import sys
from typing import TextIO


class Reporter:
    """Prints status lines unless it is quiet."""

    def __init__(self, quiet: bool = False, stream: TextIO | None = None):
        self.quiet = quiet
        self.stream = stream if stream is not None else sys.stderr
        self._progress_open = False

    def info(self, message: str) -> None:
        if self.quiet:
            return
        self._close_progress()
        print(message, file=self.stream)

    def warn(self, message: str) -> None:
        self._close_progress()
        print(f"warning: {message}", file=self.stream)

    def progress(self, done: int, total: int) -> None:
        if self.quiet:
            return
        print(f"\r  tts: {done}/{total}", end="", file=self.stream, flush=True)
        self._progress_open = True

    def progress_done(self) -> None:
        self._close_progress()

    def _close_progress(self) -> None:
        if self._progress_open:
            print(file=self.stream)
            self._progress_open = False
