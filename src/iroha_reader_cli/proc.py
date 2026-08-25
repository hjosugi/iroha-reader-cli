"""One place to run external commands.

Every engine and every ffmpeg call goes through run(), so a failing
command always turns into the same clean error message.
"""

from __future__ import annotations

import subprocess

from .errors import CommandFailedError, MissingCommandError


def run(argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run a command, capture its output, and raise a clean error on failure."""
    try:
        return subprocess.run(argv, input=stdin, check=True, capture_output=True)
    except FileNotFoundError as err:
        raise MissingCommandError(f"command not found: {argv[0]}") from err
    except subprocess.CalledProcessError as err:
        raise CommandFailedError(argv, err) from err
