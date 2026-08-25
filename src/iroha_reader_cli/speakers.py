"""`--list-speakers`: show what voices each engine offers."""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any, TextIO

from . import engines
from .engines import EngineSettings, edge, openjtalk, piper, voicevox
from .errors import EngineNotReadyError, MissingCommandError
from .proc import run


def list_speakers(settings: EngineSettings, out: TextIO | None = None) -> None:
    """Print the voices of the chosen engine."""
    stream = out if out is not None else sys.stdout
    name = settings.requested
    if name == engines.AUTO:
        # A running VOICEVOX engine is the most interesting list. Fall
        # back to the engine `auto` would actually use for the text.
        try:
            _print_voicevox(settings, stream)
            return
        except EngineNotReadyError:
            name = engines.choose(settings, japanese=True)

    if name == "voicevox":
        _print_voicevox(settings, stream)
    elif name == "openjtalk":
        _print_openjtalk(stream)
    elif name == "piper":
        _print_piper(settings, stream)
    elif name == "edge":
        _print_edge(settings, stream)
    else:
        _print_espeak(settings, stream)


def _print_voicevox(settings: EngineSettings, out: TextIO) -> None:
    data = voicevox.fetch_speakers(settings.voicevox_url, timeout=3)
    print("# voicevox styles (use the id or the name with --speaker)", file=out)
    for speaker in data:
        for style in speaker.get("styles") or []:
            print(f'{style.get("id", "?"):>4}  {speaker.get("name", "?")} '
                  f'({style.get("name", "?")})', file=out)


def _print_openjtalk(out: TextIO) -> None:
    print("# open_jtalk voices (use the name or the path with --ojt-voice)", file=out)
    voices = openjtalk.installed_voices()
    for path in voices:
        print(f"{path.stem:<32} {path}", file=out)
    if not voices:
        print("(none found. Install an hts-voice-* package, or drop a .htsvoice "
              f"file in {openjtalk.VOICE_DIRS[0]})", file=out)


def _print_piper(settings: EngineSettings, out: TextIO) -> None:
    print("# piper voices (use the name or the path with --piper-model)", file=out)
    base = Path(settings.piper_data)
    names = sorted(path.stem for path in base.rglob("*.onnx")) if base.is_dir() else []
    for name in names:
        print(name, file=out)
    if not names:
        print(f"(none found in {base})", file=out)
    print(file=out)
    print("# more voices (samples: https://rhasspy.github.io/piper-samples/):", file=out)
    print(f"#   python3 -m piper.download_voices {piper.DEFAULT_MODEL} "
          f"--download-dir {base}", file=out)


def _print_edge(settings: EngineSettings, out: TextIO) -> None:
    voices: list[Any] = asyncio.run(edge.list_voices())
    print("# edge voices (use the ShortName with --voice)", file=out)
    wanted = (settings.lang or "").lower()
    for voice in voices:
        if wanted and not str(voice["Locale"]).lower().startswith(wanted):
            continue
        print(f'{voice["ShortName"]:<42} {voice["Gender"]:<8} {voice["Locale"]}', file=out)


def _print_espeak(settings: EngineSettings, out: TextIO) -> None:
    if shutil.which(engines.EspeakEngine.command) is None:
        raise MissingCommandError("espeak-ng is missing. Install it first: "
                             "sudo apt install espeak-ng")
    argv = [engines.EspeakEngine.command]
    argv.append(f"--voices={settings.lang}" if settings.lang else "--voices")
    print("# espeak voices (use the language code with --lang)", file=out)
    print(run(argv).stdout.decode("utf-8", "replace").rstrip(), file=out)
