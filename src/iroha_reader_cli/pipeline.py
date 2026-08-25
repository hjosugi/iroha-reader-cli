"""The conversion itself: document in, audio plus subtitles out.

The order matters. Every line is synthesized on its own, each segment
is measured with ffprobe, and only then are the segments joined with
the same gaps the timeline assumes. That is why the subtitles line up
without any speech recognition or forced alignment.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import audio, extract, segment, subtitles
from .cache import CachedEngine, SegmentCache
from .engines import Engine, EngineSettings, create
from .errors import ReaderError
from .readings import Readings
from .reporting import Reporter
from .timeline import Timeline
from .timeline import build as build_timeline

AUDIO_FORMATS = ("mp3", "wav")


@dataclass(slots=True)
class ConvertOptions:
    """Everything about the output that is not engine specific."""

    outdir: Path | None = None
    name: str | None = None
    audio_format: str = "mp3"
    bitrate: str = "64k"
    loudnorm: bool = False
    subtitle_formats: tuple[str, ...] = subtitles.DEFAULT_FORMATS
    gap_ms: int = 200
    max_chars: int = segment.DEFAULT_MAX_CHARS
    pages: tuple[int, int | None] | None = None
    keep_code: bool = False
    write_text: bool = False
    readings: Readings = field(default_factory=Readings)
    #: Shown instead of the path in the log, for input that is not a real file.
    source_label: str | None = None
    use_cache: bool = True
    cache_dir: Path | None = None

    def __post_init__(self) -> None:
        # A config file or a library caller may pass plain strings.
        if self.outdir is not None:
            self.outdir = Path(self.outdir)
        if self.cache_dir is not None:
            self.cache_dir = Path(self.cache_dir)
        self.subtitle_formats = tuple(self.subtitle_formats)

    def validate(self) -> None:
        if self.audio_format not in AUDIO_FORMATS:
            raise ReaderError(f"unknown audio format: {self.audio_format}")
        unknown = [f for f in self.subtitle_formats if f not in subtitles.FORMATS]
        if unknown:
            raise ReaderError(f"unknown subtitle format: {', '.join(unknown)}")
        if self.gap_ms < 0:
            raise ReaderError("--gap-ms must be 0 or more")
        if self.max_chars < 1:
            raise ReaderError("--max-chars must be 1 or more")


@dataclass(frozen=True, slots=True)
class ConvertResult:
    """What one input file produced."""

    source: Path
    audio: Path
    subtitle_files: tuple[Path, ...]
    text_file: Path | None
    lines: tuple[str, ...]
    timeline: Timeline
    engine: str


def read_lines(path: Path, options: ConvertOptions,
               reporter: Reporter | None = None) -> list[str]:
    """Extract the file and split it into subtitle lines."""
    pages = options.pages
    if pages and path.suffix.lower() != ".pdf":
        if reporter is not None:
            reporter.warn("--pages works with pdf only. Ignoring it.")
        pages = None
    text = extract.extract(path, keep_code=options.keep_code, pages=pages)
    lines = segment.segment(text, max_chars=options.max_chars)
    if not lines:
        raise ReaderError(f"no readable text in {path}")
    return lines


def synthesize(lines: Sequence[str], engine: Engine, out_path: Path,
               options: ConvertOptions, reporter: Reporter) -> Timeline:
    """Render the lines to one audio file and return the timeline."""
    with tempfile.TemporaryDirectory(prefix="iroha_reader_") as tmp:
        segments = engine.synth_all(lines, tmp, reporter)
        timeline = build_timeline(
            [audio.duration_sec(p) for p in segments], options.gap_ms / 1000.0
        )
        pieces = list(segments)
        if options.gap_ms > 0 and len(segments) > 1:
            silence = str(Path(tmp) / f"silence.{engine.ext}")
            audio.make_silence(silence, options.gap_ms, audio.sample_rate(segments[0]))
            pieces = []
            for index, path in enumerate(segments):
                pieces.append(path)
                if index < len(segments) - 1:
                    pieces.append(silence)
        audio.concat(pieces, str(out_path),
                     bitrate=options.bitrate, loudnorm=options.loudnorm)
    return timeline


def convert(path: Path, options: ConvertOptions,
            settings: EngineSettings | None = None,
            reporter: Reporter | None = None) -> ConvertResult:
    """Convert one document into audio plus subtitles."""
    options.validate()
    settings = settings if settings is not None else EngineSettings()
    reporter = reporter if reporter is not None else Reporter(quiet=True)

    reporter.info(f"* {options.source_label or path}")
    lines = read_lines(path, options, reporter)
    reporter.info(f"  lines: {len(lines)}")

    outdir = options.outdir if options.outdir is not None else path.parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = options.name or path.stem
    audio_path = outdir / f"{stem}.{options.audio_format}"

    engine = create(settings, japanese=segment.has_japanese("".join(lines)))
    detail = f" ({engine.detail})" if engine.detail else ""
    reporter.info(f"  engine: {engine.name}{detail}")
    if options.use_cache:
        # Only the segments are cached; the join happens every time.
        engine = CachedEngine(engine, SegmentCache(options.cache_dir))

    # The dictionary changes only what is spoken.
    spoken = options.readings.apply_all(lines) if options.readings else list(lines)
    timeline = synthesize(spoken, engine, audio_path, options, reporter)

    written: list[Path] = []
    for fmt in options.subtitle_formats:
        sub_path = outdir / f"{stem}.{fmt}"
        sub_path.write_text(
            subtitles.render(fmt, lines, timeline, stem),
            encoding="utf-8", newline="\n",
        )
        written.append(sub_path)

    text_file: Path | None = None
    if options.write_text:
        text_file = outdir / f"{stem}.lines.txt"
        text_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    reporter.info(f"  wrote: {audio_path}")
    for sub_path in written:
        reporter.info(f"  wrote: {sub_path}")
    if text_file is not None:
        reporter.info(f"  wrote: {text_file}")

    return ConvertResult(
        source=path,
        audio=audio_path,
        subtitle_files=tuple(written),
        text_file=text_file,
        lines=tuple(lines),
        timeline=timeline,
        engine=engine.name,
    )
