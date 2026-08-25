"""One place to run external commands.

Every engine and every ffmpeg call goes through run(), so a failing
command always turns into the same clean error message, and the child
process always gets a clean environment.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .errors import CommandFailedError, MissingCommandError

#: Search paths a one-file build points at its own unpacked libraries.
_LIBRARY_VARS = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH")


def child_environment() -> dict[str, str] | None:
    """The environment for an external command, or None to inherit ours.

    A PyInstaller build unpacks its own libstdc++ and points
    LD_LIBRARY_PATH at it. Child processes inherit that, so the system
    ffmpeg would try to load our (older) libraries and fail with
    something like `GLIBCXX_3.4.30 not found`. PyInstaller keeps the
    original value in <VAR>_ORIG; put it back before spawning.
    """
    if not getattr(sys, "frozen", False):
        return None
    env = dict(os.environ)
    for name in _LIBRARY_VARS:
        original = env.pop(f"{name}_ORIG", None)
        if original:
            env[name] = original
        else:
            env.pop(name, None)
    return env


def run(argv: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run a command, capture its output, and raise a clean error on failure."""
    try:
        return subprocess.run(argv, input=stdin, check=True, capture_output=True,
                              env=child_environment())
    except FileNotFoundError as err:
        raise MissingCommandError(f"command not found: {argv[0]}") from err
    except subprocess.CalledProcessError as err:
        raise CommandFailedError(argv, err) from err
