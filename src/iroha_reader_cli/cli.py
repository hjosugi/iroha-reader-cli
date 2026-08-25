"""Command line for iroha-reader-cli.

This layer only parses flags and prints messages. The work happens in
pipeline.convert, which is also usable as a library.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from . import (
    __version__,
    audio,
    cache,
    completion,
    config,
    engines,
    extract,
    server,
    speakers,
    subtitles,
)
from .engines import EngineSettings, edge, openjtalk, piper, voicevox
from .errors import ReaderError
from .pipeline import (
    AUDIO_FORMATS,
    DEFAULT_CHAPTER_LEVEL,
    ConvertOptions,
    convert_all,
)
from .readings import Readings
from .reporting import Reporter
from .segment import DEFAULT_MAX_CHARS

PROG = "iroha-reader-cli"
#: The same tool, for people who type it a lot.
SHORT_PROG = "irh"


def prog_name() -> str:
    """Whichever of our two names was used to start this."""
    called = Path(sys.argv[0]).name if sys.argv else ""
    return called if called in (PROG, SHORT_PROG) else PROG

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
        prog=prog_name(),
        description="Convert md / epub / pdf / txt into audio plus synced subtitles.",
    )
    p.add_argument("inputs", nargs="*", type=Path,
                   help=f"input files ({' '.join(extract.SUPPORTED_SUFFIXES)}), "
                        "or - for stdin (see --type)")
    p.add_argument("-o", "--outdir", type=Path, default=None,
                   help="output directory (default: next to the input)")
    p.add_argument("--name", default=None,
                   help="output base name (default: the input file name). "
                        "One input file only")
    p.add_argument("--config", type=Path, default=None,
                   help=f"config file (default: {config.default_path()})")
    p.add_argument("--profile", default=None,
                   help="use a [profile.NAME] table from the config file")
    p.add_argument("--engine", choices=list(engines.ENGINE_NAMES), default=engines.AUTO,
                   help="tts engine (default: auto = openjtalk for Japanese, "
                        "piper for other languages, espeak as the fallback; "
                        "all free and local)")
    p.add_argument("--list-speakers", action="store_true",
                   help="list the voices of the chosen engine and exit")
    p.add_argument("--serve", action="store_true",
                   help="open a local web page instead: drop a document on it "
                        "and watch the text keep time with the audio")
    p.add_argument("--host", default=server.DEFAULT_HOST,
                   help=f"address for --serve (default: {server.DEFAULT_HOST})")
    p.add_argument("--port", type=int, default=server.DEFAULT_PORT,
                   help=f"port for --serve (default: {server.DEFAULT_PORT})")
    p.add_argument("--no-browser", dest="open_browser", action="store_false",
                   help="do not open a browser window for --serve")
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
    p.add_argument("--no-chapters", dest="chapters", action="store_false",
                   help="do not write markdown headings into the mp3 as chapters")
    p.add_argument("--chapter-level", type=int, default=DEFAULT_CHAPTER_LEVEL,
                   help="headings of this level or shallower become chapters "
                        f"(default: {DEFAULT_CHAPTER_LEVEL})")
    p.add_argument("--split-by-heading", dest="split_level", type=int, default=None,
                   metavar="LEVEL",
                   help="write one audio file per heading of this level, "
                        "instead of one for the whole document")
    p.add_argument("--lrc-style", choices=["line", "word"], default="line",
                   help="line: one timestamp per line. word: a timestamp per "
                        "word as well (Enhanced LRC and karaoke WebVTT). "
                        "Needs --engine edge (default: line)")
    p.add_argument("--gap-ms", type=int, default=200,
                   help="silence between lines, in ms (default: 200)")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                   help=f"max characters per subtitle line "
                        f"(default: {DEFAULT_MAX_CHARS})")
    p.add_argument("--type", dest="input_type", choices=list(extract.INPUT_TYPES),
                   default="md",
                   help="how to read stdin when the input is - (default: md)")
    p.add_argument("--pdf-backend", choices=list(extract.PDF_BACKENDS), default="auto",
                   help="how to read pdf text (default: auto = pdftotext when "
                        "poppler is installed, which reads columns in the right "
                        "order, else pypdf)")
    p.add_argument("--pages", default=None,
                   help="pdf page range, like 3-10 or 5 or 3- (default: all)")
    p.add_argument("--dict", type=Path, default=None, dest="dict_file",
                   help="reading dictionary (TSV: word<TAB>reading). "
                        "Fixes misreads; the subtitles keep the original text")
    p.add_argument("--no-cache", dest="use_cache", action="store_false",
                   help="synthesize every line again, ignoring the cache")
    p.add_argument("--cache-dir", type=Path, default=None,
                   help=f"where segments are cached (default: {cache.default_dir()})")
    p.add_argument("--cache-max-mb", type=int, default=cache.DEFAULT_MAX_MB,
                   help="how much cache to keep, in MB. 0 keeps everything "
                        f"(default: {cache.DEFAULT_MAX_MB})")
    p.add_argument("--clear-cache", action="store_true",
                   help="delete the cached segments and exit")
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
    p.add_argument("--completion", choices=list(completion.SHELLS), default=None,
                   help="print a completion script for this shell and exit")
    p.add_argument("-V", "--version", action="version",
                   version=f"{PROG} {__version__}")  # always the full name

    p.add_argument("--speed", type=float, default=1.0,
                   help="speech rate for any engine, 0.5 slow to 2.0 fast "
                        "(default: 1.0). The engine specific settings below "
                        "win over it")

    g = p.add_argument_group("openjtalk options (free, local, Japanese)")
    g.add_argument("--ojt-dict", default=openjtalk.DEFAULT_DICT,
                   help="dictionary directory")
    g.add_argument("--ojt-voice", default=openjtalk.DEFAULT_VOICE,
                   help=".htsvoice file. Swap it to change the voice")
    g.add_argument("--ojt-halftone", type=float, default=0.0,
                   help="pitch shift in half tones, like 3.0 or -2.0 (default: 0.0)")
    g.add_argument("--ojt-volume-db", type=float, default=0.0,
                   help="volume in dB, like 6.0 or -6.0 (default: 0.0)")

    g = p.add_argument_group("piper options (free, local, neural quality)")
    g.add_argument("--piper-model", default=piper.DEFAULT_MODEL,
                   help=f"voice name or .onnx path (default: {piper.DEFAULT_MODEL})")
    g.add_argument("--piper-data", type=Path, default=piper.DEFAULT_DATA_DIR,
                   help="directory with downloaded .onnx voices")
    g.add_argument("--piper-length", type=float, default=None,
                   help="length scale, bigger is slower (default: from --speed)")

    g = p.add_argument_group("espeak options (free, local, many languages)")
    g.add_argument("--lang", default=None,
                   help="voice/language, like ja or en. Variants work too, "
                        "like ja+f3 (female 3) or en+m2 (default: auto)")
    g.add_argument("--wpm", type=int, default=None,
                   help=f"words per minute (default: {engines.DEFAULT_WPM} "
                        "scaled by --speed)")
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
    g.add_argument("--vv-speed", type=float, default=None,
                   help="speedScale (default: from --speed)")
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
    g.add_argument("--rate", default=None,
                   help="speech rate, like +10%% (default: from --speed)")
    g.add_argument("--edge-pitch", default="+0Hz",
                   help="pitch, like +20Hz or -20Hz (default: +0Hz)")
    g.add_argument("--edge-volume", default="+0%",
                   help="volume, like +20%% or -20%% (default: +0%%)")
    g.add_argument("--concurrency", type=int, default=4,
                   help="parallel edge requests (default: 4)")
    g.add_argument("--min-interval-ms", type=int, default=0,
                   help="least time between edge requests, in ms. Raise it when "
                        "the service throttles you (default: 0)")
    return p


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line, with the config file as the defaults."""
    # Pass 1: find --config, so the file can supply the defaults for pass 2.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path, default=None)
    pre.add_argument("--profile", default=None)
    known, _ = pre.parse_known_args(argv)

    parser = build_parser()
    file_config = config.select_profile(config.load(known.config), known.profile)
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
    raw = args.subs
    if isinstance(raw, str):
        # A config file may write subs = "lrc,srt" instead of a list.
        raw = [item.strip() for item in raw.split(",") if item.strip()]
    formats = tuple(raw) if raw else subtitles.DEFAULT_FORMATS
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
        pdf_backend=args.pdf_backend,
        keep_code=args.keep_code,
        write_text=args.write_text,
        use_cache=args.use_cache,
        cache_dir=args.cache_dir,
        cache_max_mb=args.cache_max_mb,
        chapters=args.chapters,
        chapter_level=args.chapter_level,
        split_level=args.split_level,
        readings=Readings.load(Path(args.dict_file)) if args.dict_file else Readings(),
    )


STDIN_ARG = "-"
STDIN_NAME = "stdin"


@contextmanager
def stdin_source(kind: str, stream: IO[bytes] | None = None) -> Iterator[Path]:
    """Spool stdin to a temporary file so the normal readers can use it."""
    data = (stream if stream is not None else sys.stdin.buffer).read()
    if not data.strip():
        raise ReaderError("nothing on stdin")
    with tempfile.TemporaryDirectory(prefix="iroha_stdin_") as tmp:
        path = Path(tmp) / f"{STDIN_NAME}.{kind}"
        path.write_bytes(data)
        yield path


def _reading_stdin(inputs: Sequence[Path]) -> bool:
    if not any(str(path) == STDIN_ARG for path in inputs):
        return False
    if len(inputs) > 1:
        raise ReaderError(f"{STDIN_ARG} cannot be mixed with other input files")
    return True


def _dry_run(paths: Sequence[Path], options: ConvertOptions,
             reporter: Reporter) -> int:
    from .pipeline import read_lines

    for path in paths:
        reporter.info(f"* {options.source_label or path}")
        for line in read_lines(path, options, reporter):
            print(line.text)
    return EXIT_OK


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return an exit code."""
    args = parse_args(argv)
    reporter = Reporter(quiet=args.quiet)
    settings = EngineSettings.from_namespace(args)

    if args.completion:
        print(completion.script(args.completion, build_parser(), prog_name()), end="")
        return EXIT_OK

    if args.list_speakers:
        speakers.list_speakers(settings)
        return EXIT_OK

    if args.serve:
        audio.check_tools()
        server.serve(build_options(args), settings, reporter,
                     host=args.host, port=args.port,
                     open_browser=args.open_browser)
        return EXIT_OK

    if args.clear_cache:
        files, freed = cache.SegmentCache(args.cache_dir).clear()
        print(f"cleared {files} cached segments ({freed / 1_000_000:.1f} MB)")
        return EXIT_OK

    if not args.inputs:
        raise ReaderError(f"no input files. See {prog_name()} --help")
    if args.name and len(args.inputs) > 1:
        raise ReaderError("--name works with one input file only")

    options = build_options(args)
    options.validate()

    if _reading_stdin(args.inputs):
        with stdin_source(args.input_type) as path:
            # There is no input file to sit next to, or to be named after.
            options.outdir = options.outdir or Path.cwd()
            options.name = options.name or STDIN_NAME
            options.source_label = "(stdin)"
            if args.dry_run:
                return _dry_run([path], options, reporter)
            audio.check_tools()
            convert_all(path, options, settings, reporter)
        return EXIT_OK

    if args.dry_run:
        return _dry_run(args.inputs, options, reporter)

    audio.check_tools()
    for path in args.inputs:
        convert_all(path, options, settings, reporter)
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
