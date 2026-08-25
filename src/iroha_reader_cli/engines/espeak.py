"""espeak-ng: offline, tiny, many languages, robotic voice.

This is the fallback engine. It is the only one that is always
available on a plain Linux box.
"""

from __future__ import annotations

from ..proc import run
from .base import LocalEngine


class EspeakEngine(LocalEngine):
    """Offline engine driven by the espeak-ng command."""

    name = "espeak"
    ext = "wav"
    command = "espeak-ng"

    def __init__(self, lang: str = "ja", wpm: int = 175,
                 pitch: int | None = None, amplitude: int | None = None,
                 jobs: int = 1):
        super().__init__(jobs=jobs)
        self.lang = lang
        self.wpm = wpm
        self.pitch = pitch
        self.amplitude = amplitude

    @property
    def detail(self) -> str:
        return self.lang

    def synth_one(self, text: str, path: str) -> None:
        argv = [self.command, "-v", self.lang, "-s", str(self.wpm)]
        if self.pitch is not None:
            argv += ["-p", str(self.pitch)]
        if self.amplitude is not None:
            argv += ["-a", str(self.amplitude)]
        argv += ["-w", path, "--stdin"]
        # The text goes on stdin, so any content is safe.
        run(argv, stdin=text.encode("utf-8"))
