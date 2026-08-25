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

from . import audio, document, extract, segment, subtitles
from .audio import ChapterMark
from .cache import CachedEngine, SegmentCache
from .document import Line
from .engines import Engine, EngineSettings, create
from .errors import ReaderError
from .readings import Readings
from .reporting import Reporter
from .timeline import Timeline
from .timeline import build as build_timeline

AUDIO_FORMATS = ("mp3", "wav")
#: Chapter marks can only be written into formats that carry metadata.
CHAPTER_FORMATS = ("mp3",)
DEFAULT_CHAPTER_LEVEL = 2


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
    pdf_backend: str = "auto"
    keep_code: bool = False
    write_text: bool = False
    readings: Readings = field(default_factory=Readings)
    #: Shown instead of the path in the log, for input that is not a real file.
    source_label: str | None = None
    use_cache: bool = True
    cache_dir: Path | None = None
    #: Write markdown headings into the audio file as chapters.
    chapters: bool = True
    chapter_level: int = DEFAULT_CHAPTER_LEVEL
    #: One output per heading of this level, instead of one per file.
    split_level: int | None = None

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
        if self.pdf_backend not in extract.PDF_BACKENDS:
            raise ReaderError(f"unknown pdf backend: {self.pdf_backend}")
        if self.gap_ms < 0:
            raise ReaderError("--gap-ms must be 0 or more")
        if self.max_chars < 1:
            raise ReaderError("--max-chars must be 1 or more")
        for name, level in (("--chapter-level", self.chapter_level),
                            ("--split-by-heading", self.split_level)):
            if level is not None and not 1 <= level <= 6:
                raise ReaderError(f"{name} must be between 1 and 6")


@dataclass(frozen=True, slots=True)
class ConvertResult:
    """What one input file, or one chapter of it, produced."""

    source: Path
    audio: Path
    subtitle_files: tuple[Path, ...]
    text_file: Path | None
    lines: tuple[Line, ...]
    timeline: Timeline
    engine: str
    chapters: tuple[ChapterMark, ...] = ()

    @property
    def texts(self) -> tuple[str, ...]:
        """Just the spoken text of each line."""
        return tuple(line.text for line in self.lines)


def read_lines(path: Path, options: ConvertOptions,
               reporter: Reporter | None = None) -> list[Line]:
    """Extract the file and split it into subtitle lines."""
    pages = options.pages
    if pages and path.suffix.lower() != ".pdf":
        if reporter is not None:
            reporter.warn("--pages works with pdf only. Ignoring it.")
        pages = None
    blocks = extract.extract_blocks(path, keep_code=options.keep_code, pages=pages,
                                    pdf_backend=options.pdf_backend)
    lines = segment.segment_blocks(blocks, max_chars=options.max_chars)
    if not lines:
        raise ReaderError(f"no readable text in {path}")
    return lines


def chapter_marks(lines: Sequence[Line], timeline: Timeline, level: int,
                  title: str = "") -> list[ChapterMark]:
    """Turn the headings into chapter marks over the finished audio."""
    parts = document.chapters(lines, level, title=title)
    if len(parts) < 2:
        return []
    marks: list[ChapterMark] = []
    for part in parts:
        start = timeline.starts[part.start] if part.start < len(timeline.starts) else 0.0
        end = (timeline.starts[part.stop] if part.stop < len(timeline.starts)
               else timeline.total)
        marks.append(ChapterMark(part.title, start, end))
    return marks


def synthesize(lines: Sequence[str], engine: Engine, out_path: Path,
               options: ConvertOptions, reporter: Reporter) -> Timeline:
    """Render the lines to one audio file and return the timeline."""
    with tempfile.TemporaryDirectory(prefix="iroha_reader_") as tmp:
        segments = engine.synth_all(lines, tmp, reporter)
        paths = segments.paths
        timeline = build_timeline(
            [audio.duration_sec(p) for p in paths],
            options.gap_ms / 1000.0,
            words=segments.words,
        )
        pieces = list(paths)
        if options.gap_ms > 0 and len(paths) > 1:
            silence = str(Path(tmp) / f"silence.{engine.ext}")
            audio.make_silence(silence, options.gap_ms, audio.sample_rate(paths[0]))
            pieces = []
            for index, path in enumerate(paths):
                pieces.append(path)
                if index < len(paths) - 1:
                    pieces.append(silence)
        audio.concat(pieces, str(out_path),
                     bitrate=options.bitrate, loudnorm=options.loudnorm)
    return timeline


def _open(path: Path, options: ConvertOptions, settings: EngineSettings,
          reporter: Reporter) -> tuple[list[Line], Path, str, Engine]:
    """Read the document and get an engine ready for it."""
    reporter.info(f"* {options.source_label or path}")
    lines = read_lines(path, options, reporter)
    reporter.info(f"  lines: {len(lines)}")

    outdir = options.outdir if options.outdir is not None else path.parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = options.name or path.stem

    engine = create(settings, japanese=segment.has_japanese(
        "".join(line.text for line in lines)))
    detail = f" ({engine.detail})" if engine.detail else ""
    reporter.info(f"  engine: {engine.name}{detail}")
    if options.use_cache:
        # Only the segments are cached; the join happens every time.
        engine = CachedEngine(engine, SegmentCache(options.cache_dir))
    return lines, outdir, stem, engine


def _render(lines: Sequence[Line], source: Path, outdir: Path, stem: str,
            options: ConvertOptions, engine: Engine,
            reporter: Reporter) -> ConvertResult:
    """Synthesize one run of lines and write everything that goes with it."""
    texts = document.texts(lines)
    audio_path = outdir / f"{stem}.{options.audio_format}"

    # The dictionary changes only what is spoken.
    spoken = options.readings.apply_all(texts) if options.readings else list(texts)
    timeline = synthesize(spoken, engine, audio_path, options, reporter)

    marks: tuple[ChapterMark, ...] = ()
    if options.chapters and options.audio_format in CHAPTER_FORMATS:
        marks = tuple(chapter_marks(lines, timeline, options.chapter_level, stem))
        if marks:
            # Rewriting the tags is cheaper than a second synthesis pass.
            audio.write_chapters(str(audio_path), marks, title=stem)
            reporter.info(f"  chapters: {len(marks)}")

    written: list[Path] = []
    for fmt in options.subtitle_formats:
        sub_path = outdir / f"{stem}.{fmt}"
        sub_path.write_text(subtitles.render(fmt, texts, timeline, stem),
                            encoding="utf-8", newline="\n")
        written.append(sub_path)

    text_file: Path | None = None
    if options.write_text:
        text_file = outdir / f"{stem}.lines.txt"
        text_file.write_text("\n".join(texts) + "\n", encoding="utf-8", newline="\n")

    reporter.info(f"  wrote: {audio_path}")
    for sub_path in written:
        reporter.info(f"  wrote: {sub_path}")
    if text_file is not None:
        reporter.info(f"  wrote: {text_file}")

    return ConvertResult(
        source=source,
        audio=audio_path,
        subtitle_files=tuple(written),
        text_file=text_file,
        lines=tuple(lines),
        timeline=timeline,
        engine=engine.name,
        chapters=marks,
    )


def convert(path: Path, options: ConvertOptions,
            settings: EngineSettings | None = None,
            reporter: Reporter | None = None) -> ConvertResult:
    """Convert one document into one audio file plus subtitles.

    Splitting is ignored here; use convert_all() for that.
    """
    options.validate()
    settings = settings if settings is not None else EngineSettings()
    reporter = reporter if reporter is not None else Reporter(quiet=True)
    lines, outdir, stem, engine = _open(path, options, settings, reporter)
    return _render(lines, path, outdir, stem, options, engine, reporter)


def convert_all(path: Path, options: ConvertOptions,
                settings: EngineSettings | None = None,
                reporter: Reporter | None = None) -> list[ConvertResult]:
    """Convert one document, honouring --split-by-heading.

    Without splitting this is convert() in a list of one.
    """
    options.validate()
    settings = settings if settings is not None else EngineSettings()
    reporter = reporter if reporter is not None else Reporter(quiet=True)
    lines, outdir, stem, engine = _open(path, options, settings, reporter)

    if options.split_level is None:
        return [_render(lines, path, outdir, stem, options, engine, reporter)]

    parts = document.chapters(lines, options.split_level, title=stem)
    reporter.info(f"  chapters: {len(parts)}")
    results: list[ConvertResult] = []
    for number, part in enumerate(parts, start=1):
        name = f"{stem}-{number:02d}-{document.slug(part.title, f'part{number}')}"
        reporter.info(f"  [{number}/{len(parts)}] {part.title}")
        results.append(_render(part.lines, path, outdir, name, options, engine,
                               reporter))
    return results
