"""Open JTalk: offline Japanese, free and open source.

Better Japanese than espeak and it needs no server, so `auto` picks
it first for Japanese text.
"""

from __future__ import annotations

from pathlib import Path

from ..proc import run
from .base import LocalEngine

#: Paths that the Debian/Ubuntu packages use.
DEFAULT_DICT = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
DEFAULT_VOICE = (
    "/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"
)
#: Searched by --list-speakers.
VOICE_DIRS = ("/usr/share/hts-voice", "/usr/local/share/hts-voice")

INSTALL_HINT = (
    "install it first (Debian/Ubuntu):\n"
    "  sudo apt install open-jtalk open-jtalk-mecab-naist-jdic "
    "hts-voice-nitech-jp-atr503-m001"
)


class OpenJTalkEngine(LocalEngine):
    """Offline Japanese engine driven by the open_jtalk command."""

    name = "openjtalk"
    ext = "wav"
    command = "open_jtalk"

    def __init__(self, dict_dir: str, voice: str, speed: float = 1.0,
                 halftone: float = 0.0, volume_db: float = 0.0,
                 jobs: int = 1):
        super().__init__(jobs=jobs)
        self.dict_dir = dict_dir
        self.voice = voice
        self.speed = speed
        self.halftone = halftone
        self.volume_db = volume_db

    @property
    def detail(self) -> str:
        return Path(self.voice).stem

    def synth_one(self, text: str, path: str) -> None:
        # The text goes on stdin, so any content is safe.
        run(
            [
                self.command,
                "-x", self.dict_dir,
                "-m", self.voice,
                "-r", str(self.speed),
                "-fm", str(self.halftone),
                "-g", str(self.volume_db),
                "-ow", path,
            ],
            stdin=text.encode("utf-8"),
        )
