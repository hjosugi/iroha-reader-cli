"""Piper: offline neural voices, high quality, 30+ languages.

Piper is a separate GPL-3.0 project (github.com/OHF-Voice/piper1-gpl).
It is called as an external command, like ffmpeg, so this package
stays MIT.
"""

from __future__ import annotations

from pathlib import Path

from ..proc import run
from .base import LocalEngine

DEFAULT_MODEL = "en_US-lessac-medium"
DEFAULT_DATA_DIR = Path.home() / ".local/share/iroha-reader-cli/piper"

INSTALL_HINT = (
    "install it and download a voice:\n"
    "  uv tool install piper-tts     # or: pip install piper-tts\n"
    "  mkdir -p {data}\n"
    "  python3 -m piper.download_voices {model} --download-dir {data}"
)


def resolve_model(model: str, data_dir: Path) -> str | None:
    """Return the .onnx path for a voice name or path, or None."""
    direct = Path(model)
    if direct.is_file():
        return str(direct)
    candidate = data_dir / f"{model}.onnx"
    if candidate.is_file():
        return str(candidate)
    return None


def install_hint(model: str, data_dir: Path) -> str:
    return INSTALL_HINT.format(model=model, data=data_dir)


class PiperEngine(LocalEngine):
    """Offline neural engine driven by the piper command."""

    name = "piper"
    ext = "wav"
    command = "piper"

    def __init__(self, model: str, length_scale: float = 1.0, jobs: int = 1):
        super().__init__(jobs=jobs)
        self.model = model
        self.length_scale = length_scale

    @property
    def detail(self) -> str:
        return Path(self.model).stem

    def synth_one(self, text: str, path: str) -> None:
        # The text goes on stdin, so any content is safe.
        run(
            [
                self.command,
                "-m", self.model,
                "-f", path,
                "--length-scale", str(self.length_scale),
            ],
            stdin=text.encode("utf-8"),
        )
