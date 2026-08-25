"""Errors that the command line turns into a clean message.

The core raises these instead of calling sys.exit, so the modules stay
usable as a library.
"""

from __future__ import annotations

import subprocess


class ReaderError(Exception):
    """A problem the user can fix. Printed as `error: <message>`."""


class UnsupportedInputError(ReaderError):
    """The input file type has no extractor."""


class MissingCommandError(ReaderError):
    """A required external command is not installed."""


class EngineNotReadyError(ReaderError):
    """The chosen TTS engine is installed but not usable yet."""


class CommandFailedError(ReaderError):
    """An external command exited with a non-zero status."""

    def __init__(self, argv: list[str], err: subprocess.CalledProcessError):
        self.argv = argv
        self.returncode = err.returncode
        detail = _tail(err.stderr) or _tail(err.stdout)
        message = f"{argv[0]} failed (exit {err.returncode})"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


def _tail(stream: bytes | str | None, lines: int = 3) -> str:
    """Return the last few lines of a captured stream, as one string."""
    if not stream:
        return ""
    text = stream.decode("utf-8", "replace") if isinstance(stream, bytes) else stream
    kept = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return " / ".join(kept[-lines:])
