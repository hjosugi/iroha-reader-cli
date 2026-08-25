"""TTS engines and the rules that pick one.

`auto` prefers the best free local engine for the text: Open JTalk
for Japanese, Piper for everything else, and espeak-ng when neither
is installed.
"""

from __future__ import annotations

import dataclasses
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import EngineNotReadyError, ReaderError
from . import openjtalk, piper, voicevox
from .base import Engine, LocalEngine
from .edge import DEFAULT_VOICE_EN, DEFAULT_VOICE_JA, EdgeEngine
from .espeak import EspeakEngine
from .openjtalk import OpenJTalkEngine
from .piper import PiperEngine
from .voicevox import VoicevoxEngine

__all__ = [
    "AUTO",
    "ENGINE_NAMES",
    "EdgeEngine",
    "Engine",
    "EngineSettings",
    "EspeakEngine",
    "LocalEngine",
    "OpenJTalkEngine",
    "PiperEngine",
    "VoicevoxEngine",
    "choose",
    "create",
]

AUTO = "auto"
ENGINE_NAMES = (AUTO, "espeak", "openjtalk", "piper", "voicevox", "edge")
#: espeak's own default, and the pace --speed scales.
DEFAULT_WPM = 175


@dataclass(slots=True)
class EngineSettings:
    """Every engine knob, filled from the command line or the config file.

    `speed` works for every engine. The engine specific speed settings
    default to None and win over it when they are set, so
    `--speed 1.3` is the simple way and `--wpm 220` is the exact one.
    """

    requested: str = AUTO
    jobs: int = 4
    #: 1.0 is the engine's own pace. Bigger is faster, everywhere.
    speed: float = 1.0

    # open jtalk
    ojt_dict: str = openjtalk.DEFAULT_DICT
    ojt_voice: str = openjtalk.DEFAULT_VOICE
    ojt_halftone: float = 0.0
    ojt_volume_db: float = 0.0

    # piper
    piper_model: str = piper.DEFAULT_MODEL
    piper_data: Path = field(default_factory=lambda: piper.DEFAULT_DATA_DIR)
    piper_length: float | None = None

    # espeak
    lang: str | None = None
    wpm: int | None = None
    es_pitch: int | None = None
    es_amp: int | None = None

    # voicevox
    voicevox_url: str = voicevox.DEFAULT_URL
    speaker: str = voicevox.DEFAULT_SPEAKER
    vv_speed: float | None = None
    vv_pitch: float = 0.0
    vv_intonation: float = 1.0
    vv_volume: float = 1.0

    # edge
    voice: str | None = None
    rate: str | None = None
    edge_pitch: str = "+0Hz"
    edge_volume: str = "+0%"
    concurrency: int = 4
    min_interval_ms: int = 0
    #: Ask the engine for per-word times. Only edge can report them.
    word_timing: bool = False

    def __post_init__(self) -> None:
        # A config file may pass this as a plain string.
        self.piper_data = Path(self.piper_data)
        if self.speed <= 0:
            raise ReaderError("--speed must be greater than 0")

    def espeak_wpm(self) -> int:
        """Words per minute, scaled by --speed unless --wpm says otherwise."""
        if self.wpm is not None:
            return self.wpm
        return max(20, round(DEFAULT_WPM * self.speed))

    def piper_length_scale(self) -> float:
        """Piper measures the other way round: bigger is slower."""
        if self.piper_length is not None:
            return self.piper_length
        return 1.0 / self.speed

    def voicevox_speed(self) -> float:
        return self.vv_speed if self.vv_speed is not None else self.speed

    def edge_rate(self) -> str:
        """Edge takes a percentage difference, like +30%."""
        if self.rate is not None:
            return self.rate
        return f"{round((self.speed - 1) * 100):+d}%"

    @classmethod
    def from_namespace(cls, args: Any) -> EngineSettings:
        """Copy the matching attributes off an argparse namespace."""
        names = {f.name for f in dataclasses.fields(cls)}
        values = {k: v for k, v in vars(args).items() if k in names}
        if hasattr(args, "engine"):
            values["requested"] = args.engine
        if hasattr(args, "lrc_style"):
            values["word_timing"] = args.lrc_style == "word"
        return cls(**values)


def openjtalk_available(settings: EngineSettings) -> bool:
    """True when open_jtalk and both of its data files are present."""
    return (
        shutil.which(OpenJTalkEngine.command) is not None
        and Path(settings.ojt_dict).is_dir()
        and openjtalk.resolve_voice(settings.ojt_voice) is not None
    )


def piper_available(settings: EngineSettings) -> bool:
    """True when piper and the chosen voice are present."""
    return (
        shutil.which(PiperEngine.command) is not None
        and piper.resolve_model(settings.piper_model, Path(settings.piper_data)) is not None
    )


def choose(settings: EngineSettings, japanese: bool) -> str:
    """Resolve `auto` to a concrete engine name."""
    if settings.requested != AUTO:
        return settings.requested
    if japanese:
        return "openjtalk" if openjtalk_available(settings) else "espeak"
    return "piper" if piper_available(settings) else "espeak"


def create(settings: EngineSettings, japanese: bool) -> Engine:
    """Build the engine for these settings and this text."""
    name = choose(settings, japanese)

    if settings.word_timing and name != "edge":
        raise EngineNotReadyError(
            f"word level timing needs --engine edge, not {name}. Only that "
            "engine reports where each word falls; the local engines would "
            "have to guess, and guessed timestamps are worse than none."
        )

    if name == "openjtalk":
        voice = openjtalk.resolve_voice(settings.ojt_voice)
        ready = (shutil.which(OpenJTalkEngine.command) is not None
                 and Path(settings.ojt_dict).is_dir())
        if not ready:
            raise EngineNotReadyError(f"open_jtalk is not ready. {openjtalk.INSTALL_HINT}")
        if voice is None:
            known = ", ".join(path.stem for path in openjtalk.installed_voices())
            raise EngineNotReadyError(
                f"no such open_jtalk voice: {settings.ojt_voice}. "
                + (f"Installed: {known}" if known
                   else "No .htsvoice file found. " + openjtalk.INSTALL_HINT)
            )
        return OpenJTalkEngine(
            settings.ojt_dict, voice, speed=settings.speed,
            halftone=settings.ojt_halftone, volume_db=settings.ojt_volume_db,
            jobs=settings.jobs,
        )

    if name == "piper":
        data_dir = Path(settings.piper_data)
        model = piper.resolve_model(settings.piper_model, data_dir)
        if shutil.which(PiperEngine.command) is None or model is None:
            raise EngineNotReadyError(
                "piper is not ready. "
                + piper.install_hint(settings.piper_model, data_dir)
            )
        return PiperEngine(model, length_scale=settings.piper_length_scale(),
                           jobs=settings.jobs)

    if name == "voicevox":
        return VoicevoxEngine(
            url=settings.voicevox_url,
            speaker=voicevox.resolve_speaker(str(settings.speaker), settings.voicevox_url),
            speed=settings.voicevox_speed(), pitch=settings.vv_pitch,
            intonation=settings.vv_intonation, volume=settings.vv_volume,
            jobs=settings.jobs,
        )

    if name == "edge":
        voice = settings.voice or (DEFAULT_VOICE_JA if japanese else DEFAULT_VOICE_EN)
        return EdgeEngine(
            voice, rate=settings.edge_rate(), pitch=settings.edge_pitch,
            volume=settings.edge_volume, concurrency=settings.concurrency,
            word_timing=settings.word_timing,
            min_interval_ms=settings.min_interval_ms,
        )

    if shutil.which(EspeakEngine.command) is None:
        raise EngineNotReadyError(
            "espeak-ng is missing. Install it first (Debian/Ubuntu):\n"
            "  sudo apt install espeak-ng"
        )
    return EspeakEngine(
        lang=settings.lang or ("ja" if japanese else "en"),
        wpm=settings.espeak_wpm(), pitch=settings.es_pitch, amplitude=settings.es_amp,
        jobs=settings.jobs,
    )
