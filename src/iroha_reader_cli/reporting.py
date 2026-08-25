"""Progress and status output.

Everything goes to stderr so that stdout stays clean for piping
(`--dry-run` writes the lines themselves to stdout).
"""

from __future__ import annotations

import sys
from typing import TextIO

#: How many progress lines a log file gets for one run.
LOG_STEPS = 10


class Reporter:
    """Prints status lines unless it is quiet.

    On a terminal the progress counter rewrites one line. Anywhere else
    -- a log file, a pipe, CI -- that would be tens of thousands of
    carriage returns, so it prints a handful of lines instead.
    """

    def __init__(self, quiet: bool = False, stream: TextIO | None = None):
        self.quiet = quiet
        self.stream = stream if stream is not None else sys.stderr
        self.interactive = bool(getattr(self.stream, "isatty", None)
                                and self.stream.isatty())
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
        if self.interactive:
            print(f"\r  tts: {done}/{total}", end="", file=self.stream, flush=True)
            self._progress_open = True
            return
        step = max(1, total // LOG_STEPS)
        if done == total or done % step == 0:
            print(f"  tts: {done}/{total}", file=self.stream, flush=True)

    def progress_done(self) -> None:
        self._close_progress()

    def _close_progress(self) -> None:
        if self._progress_open:
            print(file=self.stream)
            self._progress_open = False
