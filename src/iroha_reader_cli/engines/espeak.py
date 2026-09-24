"""espeak-ng: offline, tiny, many languages, robotic voice.

This is the fallback engine. It is the only one that is always
available on a plain Linux box, and one package away on macOS and
Windows.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .. import install
from ..proc import run
from .base import LocalEngine

#: Where the Windows installer (espeak-ng.msi) puts it. It does not
#: touch PATH, so look there too.
_WINDOWS_DIRS = ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")


def find_command() -> str | None:
    """The espeak-ng executable: from PATH, or where the Windows installer puts it."""
    found = shutil.which(EspeakEngine.command)
    if found is not None or install.family() != "win32":
        return found
    for variable in _WINDOWS_DIRS:
        base = os.environ.get(variable)
        if base and (candidate := Path(base) / "eSpeak NG" / "espeak-ng.exe").is_file():
            return str(candidate)
    return None


def missing_message() -> str:
    return f"espeak-ng is missing. Install it first {install.hint('espeak-ng')}"


class EspeakEngine(LocalEngine):
    """Offline engine driven by the espeak-ng command."""

    name = "espeak"
    ext = "wav"
    command = "espeak-ng"

    def __init__(self, lang: str = "ja", wpm: int = 175,
                 pitch: int | None = None, amplitude: int | None = None,
                 jobs: int = 1):
        super().__init__(jobs=jobs)
        self.executable = find_command() or self.command
        self.lang = lang
        self.wpm = wpm
        self.pitch = pitch
        self.amplitude = amplitude

    @property
    def detail(self) -> str:
        return self.lang

    def synth_one(self, text: str, path: str) -> None:
        argv = [self.executable, "-v", self.lang, "-s", str(self.wpm)]
        if self.pitch is not None:
            argv += ["-p", str(self.pitch)]
        if self.amplitude is not None:
            argv += ["-a", str(self.amplitude)]
        argv += ["-w", path, "--stdin"]
        # The text goes on stdin, so any content is safe.
        run(argv, stdin=text.encode("utf-8"))
