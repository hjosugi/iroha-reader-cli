"""Command line for iroha-reader-cli.

This layer only parses flags and prints messages. The work happens in
pipeline.convert, which is also usable as a library.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__, audio, config, engines, extract, speakers, subtitles
from .engines import EngineSettings, edge, openjtalk, piper, voicevox
from .errors import ReaderError
from .pipeline import AUDIO_FORMATS, ConvertOptions, convert
from .readings import Readings
from .reporting import Reporter
from .segment import DEFAULT_MAX_CHARS

PROG = "iroha-reader-cli"

#: Config keys whose name differs from the argparse destination.
CONFIG_ALIASES = {"dict": "dict_file", "format": "audio_format"}

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130


class _CommaAppend(argparse.Action):
    """Append values, splitting on commas.

    The first use on the command line replaces whatever the config
    file set, so `--subs srt` never silently keeps the config list.
    """

    def __call__(self, _parser: argparse.ArgumentParser, namespace: argparse.Namespace,
                 values: Any, _option_string: str | None = None) -> None:
        seen = f"_{self.dest}_seen"
        current: list[str] = [] if not getattr(namespace, seen, False) else list(
            getattr(namespace, self.dest) or []
        )
        setattr(namespace, seen, True)
        for value in str(values).split(","):
            item = value.strip()
            if item and item not in current:
                current.append(item)
        setattr(namespace, self.dest, current)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="Convert md / pdf / txt into audio plus synced subtitles.",
    )
    p.add_argument("inputs", nargs="*", type=Path,
                   help=f"input files ({' '.join(extract.SUPPORTED_SUFFIXES)})")
    p.add_argument("-o", "--outdir", type=Path, default=None,
                   help="output directory (default: next to the input)")
    p.add_argument("--name", default=None,
                   help="output base name (default: the input file name). "
                        "One input file only")
    p.add_argument("--config", type=Path, default=None,
                   help=f"config file (default: {config.default_path()})")
    p.add_argument("--engine", choices=list(engines.ENGINE_NAMES), default=engines.AUTO,
                   help="tts engine (default: auto = openjtalk for Japanese, "
                        "piper for other languages, espeak as the fallback; "
                        "all free and local)")
    p.add_argument("--list-speakers", action="store_true",
                   help="list the voices of the chosen engine and exit")
    p.add_argument("--format", dest="audio_format", choices=list(AUDIO_FORMATS),
                   default="mp3", help="output audio format (default: mp3)")
    p.add_argument("--bitrate", default="64k",
                   help="mp3 bitrate, like 128k (default: 64k)")
    p.add_argument("--loudnorm", action="store_true",
                   help="normalize loudness with the ffmpeg loudnorm filter")
    p.add_argument("--subs", action=_CommaAppend, default=None, metavar="FORMAT",
                   help="subtitle formats: "
                        f"{', '.join(subtitles.FORMATS)}. Repeat or use commas, "
                        "like --subs lrc,srt (default: lrc)")
    p.add_argument("--gap-ms", type=int, default=200,
                   help="silence between lines, in ms (default: 200)")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                   help=f"max characters per subtitle line "
                        f"(default: {DEFAULT_MAX_CHARS})")
    p.add_argument("--pages", default=None,
                   help="pdf page range, like 3-10 or 5 or 3- (default: all)")
    p.add_argument("--dict", type=Path, default=None, dest="dict_file",
                   help="reading dictionary (TSV: word<TAB>reading). "
                        "Fixes misreads; the subtitles keep the original text")
    p.add_argument("--jobs", type=int, default=4,
                   help="parallel lines for the local engines (default: 4)")
    p.add_argument("--keep-code", action="store_true",
                   help="read markdown code blocks out loud too")
    p.add_argument("--write-text", action="store_true",
                   help="also save the extracted lines as a .lines.txt file")
    p.add_argument("--dry-run", action="store_true",
                   help="print the lines and exit, no audio")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="no progress output, errors only")
    p.add_argument("-V", "--version", action="version",
                   version=f"{PROG} {__version__}")

    g = p.add_argument_group("openjtalk options (free, local, Japanese)")
    g.add_argument("--ojt-dict", default=openjtalk.DEFAULT_DICT,
                   help="dictionary directory")
    g.add_argument("--ojt-voice", default=openjtalk.DEFAULT_VOICE,
                   help=".htsvoice file. Swap it to change the voice")
    g.add_argument("--speed", type=float, default=1.0,
                   help="speech rate, 0.5 slow to 2.0 fast (default: 1.0)")
    g.add_argument("--ojt-halftone", type=float, default=0.0,
                   help="pitch shift in half tones, like 3.0 or -2.0 (default: 0.0)")
    g.add_argument("--ojt-volume-db", type=float, default=0.0,
                   help="volume in dB, like 6.0 or -6.0 (default: 0.0)")

    g = p.add_argument_group("piper options (free, local, neural quality)")
    g.add_argument("--piper-model", default=piper.DEFAULT_MODEL,
                   help=f"voice name or .onnx path (default: {piper.DEFAULT_MODEL})")
    g.add_argument("--piper-data", type=Path, default=piper.DEFAULT_DATA_DIR,
                   help="directory with downloaded .onnx voices")
    g.add_argument("--piper-length", type=float, default=1.0,
                   help="length scale, bigger is slower (default: 1.0)")

    g = p.add_argument_group("espeak options (free, local, many languages)")
    g.add_argument("--lang", default=None,
                   help="voice/language, like ja or en. Variants work too, "
                        "like ja+f3 (female 3) or en+m2 (default: auto)")
    g.add_argument("--wpm", type=int, default=175,
                   help="words per minute (default: 175)")
    g.add_argument("--es-pitch", type=int, default=None,
                   help="pitch 0-99 (default: the engine default, 50)")
    g.add_argument("--es-amp", type=int, default=None,
                   help="amplitude 0-200 (default: the engine default, 100)")

    g = p.add_argument_group("voicevox options (free, local server, Japanese)")
    g.add_argument("--voicevox-url", default=voicevox.DEFAULT_URL,
                   help=f"engine url (default: {voicevox.DEFAULT_URL})")
    g.add_argument("--speaker", default=voicevox.DEFAULT_SPEAKER,
                   help="style id, speaker name, or name:style. Examples: "
                        "8 / Zundamon / Zundamon:Amaama (default: 3). "
                        "See --list-speakers")
    g.add_argument("--vv-speed", type=float, default=1.0, help="speedScale (default: 1.0)")
    g.add_argument("--vv-pitch", type=float, default=0.0,
                   help="pitchScale, small values like 0.05 (default: 0.0)")
    g.add_argument("--vv-intonation", type=float, default=1.0,
                   help="intonationScale (default: 1.0)")
    g.add_argument("--vv-volume", type=float, default=1.0,
                   help="volumeScale (default: 1.0)")

    g = p.add_argument_group("edge options (no charge, online, unofficial)")
    g.add_argument("--voice", default=None,
                   help=f"voice name (default: {edge.DEFAULT_VOICE_JA} for "
                        f"Japanese, {edge.DEFAULT_VOICE_EN} otherwise)")
    g.add_argument("--rate", default="+0%",
                   help="speech rate, like +10%% (default: +0%%)")
    g.add_argument("--edge-pitch", default="+0Hz",
                   help="pitch, like +20Hz or -20Hz (default: +0Hz)")
    g.add_argument("--edge-volume", default="+0%",
                   help="volume, like +20%% or -20%% (default: +0%%)")
    g.add_argument("--concurrency", type=int, default=4,
                   help="parallel edge requests (default: 4)")
    return p


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line, with the config file as the defaults."""
    # Pass 1: find --config, so the file can supply the defaults for pass 2.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path, default=None)
    known, _ = pre.parse_known_args(argv)

    parser = build_parser()
    file_config = config.load(known.config)
    if file_config:
        valid = set(vars(parser.parse_args([])))
        defaults, unknown = config.to_defaults(file_config, valid, CONFIG_ALIASES)
        for key in unknown:
            print(f"warning: unknown config key: {key}", file=sys.stderr)
        parser.set_defaults(**defaults)

    args = parser.parse_args(list(argv) if argv is not None else None)
    # Drop the bookkeeping attribute that _CommaAppend uses.
    for name in [n for n in vars(args) if n.startswith("_")]:
        delattr(args, name)
    return args


def build_options(args: argparse.Namespace) -> ConvertOptions:
    """Turn parsed flags into pipeline options."""
    formats = tuple(args.subs) if args.subs else subtitles.DEFAULT_FORMATS
    return ConvertOptions(
        outdir=Path(args.outdir) if args.outdir else None,
        name=args.name,
        audio_format=args.audio_format,
        bitrate=args.bitrate,
        loudnorm=args.loudnorm,
        subtitle_formats=formats,
        gap_ms=args.gap_ms,
        max_chars=args.max_chars,
        pages=extract.parse_page_range(args.pages) if args.pages else None,
        keep_code=args.keep_code,
        write_text=args.write_text,
        readings=Readings.load(Path(args.dict_file)) if args.dict_file else Readings(),
    )


def _dry_run(args: argparse.Namespace, options: ConvertOptions,
             reporter: Reporter) -> int:
    from .pipeline import read_lines

    for path in args.inputs:
        reporter.info(f"* {path}")
        for line in read_lines(path, options, reporter):
            print(line)
    return EXIT_OK


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return an exit code."""
    args = parse_args(argv)
    reporter = Reporter(quiet=args.quiet)
    settings = EngineSettings.from_namespace(args)

    if args.list_speakers:
        speakers.list_speakers(settings)
        return EXIT_OK

    if not args.inputs:
        raise ReaderError(f"no input files. See {PROG} --help")
    if args.name and len(args.inputs) > 1:
        raise ReaderError("--name works with one input file only")

    options = build_options(args)
    options.validate()

    if args.dry_run:
        return _dry_run(args, options, reporter)

    audio.check_tools()
    for path in args.inputs:
        convert(path, options, settings, reporter)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Turns errors into one clean line on stderr."""
    try:
        return run(argv)
    except ReaderError as err:
        print(f"error: {err}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:  # pragma: no cover - happens under `| head`
        return EXIT_OK
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
