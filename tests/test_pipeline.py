"""The conversion itself, with the audio tools stubbed out."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from iroha_reader_cli import audio, pipeline
from iroha_reader_cli.engines.base import Engine, Segments
from iroha_reader_cli.errors import ReaderError
from iroha_reader_cli.pipeline import ConvertOptions, convert, convert_all
from iroha_reader_cli.readings import Readings
from iroha_reader_cli.reporting import Reporter

SEGMENT_SEC = 2.0
WRITTEN_CHAPTERS: list[tuple[str, list[object], str]] = []


class FakeEngine(Engine):
    """Records the spoken text and writes empty segment files."""

    name = "fake"
    ext = "wav"

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> Segments:
        self.spoken = list(lines)
        paths = self.segment_paths(len(lines), outdir)
        for path in paths:
            Path(path).write_bytes(b"")
        reporter.progress_done()
        return Segments(paths)


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> FakeEngine:
    engine = FakeEngine()
    monkeypatch.setattr(pipeline, "create", lambda _s, japanese: engine)  # noqa: ARG005
    monkeypatch.setattr(audio, "duration_sec", lambda _p: SEGMENT_SEC)
    monkeypatch.setattr(audio, "sample_rate", lambda _p: 22050)
    monkeypatch.setattr(audio, "make_silence",
                        lambda path, _ms, _rate: Path(path).write_bytes(b""))
    monkeypatch.setattr(
        audio, "concat",
        lambda paths, out, **_kw: Path(out).write_bytes(b"audio" * len(paths)),
    )
    monkeypatch.setattr(audio, "write_chapters",
                        lambda path, chapters, title="": WRITTEN_CHAPTERS.append(
                            (path, list(chapters), title)))
    WRITTEN_CHAPTERS.clear()
    return engine


def write_source(tmp_path: Path, text: str = "First line.\n\nSecond line.\n") -> Path:
    path = tmp_path / "notes.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_convert_writes_audio_and_the_asked_for_subtitles(
    tmp_path: Path, fake_engine: FakeEngine
) -> None:
    source = write_source(tmp_path)
    result = convert(source, ConvertOptions(subtitle_formats=("lrc", "srt", "vtt")))

    assert result.audio == tmp_path / "notes.mp3"
    assert result.audio.exists()
    assert [p.suffix for p in result.subtitle_files] == [".lrc", ".srt", ".vtt"]
    assert all(p.exists() for p in result.subtitle_files)
    assert result.engine == "fake"
    assert result.texts == ("First line.", "Second line.")


def test_timeline_matches_the_gap_setting(tmp_path: Path, fake_engine: FakeEngine) -> None:
    result = convert(write_source(tmp_path), ConvertOptions(gap_ms=500))
    assert result.timeline.starts == (0.0, SEGMENT_SEC + 0.5)
    assert result.timeline.total == pytest.approx(2 * SEGMENT_SEC + 0.5)


def test_readings_change_the_audio_but_not_the_subtitles(
    tmp_path: Path, fake_engine: FakeEngine
) -> None:
    source = write_source(tmp_path, "DWH is here.\n")
    options = ConvertOptions(readings=Readings.parse("DWH\tデータウェアハウス"))
    result = convert(source, options)

    assert fake_engine.spoken == ["データウェアハウス is here."]
    assert result.texts == ("DWH is here.",)
    assert "DWH is here." in result.subtitle_files[0].read_text(encoding="utf-8")


def test_outdir_and_name_are_honoured(tmp_path: Path, fake_engine: FakeEngine) -> None:
    out = tmp_path / "deep" / "dir"
    result = convert(write_source(tmp_path),
                     ConvertOptions(outdir=out, name="lesson", audio_format="wav"))
    assert result.audio == out / "lesson.wav"
    assert result.subtitle_files[0] == out / "lesson.lrc"


def test_write_text_saves_the_lines(tmp_path: Path, fake_engine: FakeEngine) -> None:
    result = convert(write_source(tmp_path), ConvertOptions(write_text=True))
    assert result.text_file is not None
    assert result.text_file.read_text(encoding="utf-8") == "First line.\nSecond line.\n"


def test_an_empty_document_is_an_error(tmp_path: Path, fake_engine: FakeEngine) -> None:
    source = tmp_path / "empty.md"
    source.write_text("```\ncode only\n```\n", encoding="utf-8")
    with pytest.raises(ReaderError, match="no readable text"):
        convert(source, ConvertOptions())


def test_pages_on_a_non_pdf_warns_and_continues(
    tmp_path: Path, fake_engine: FakeEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    convert(write_source(tmp_path), ConvertOptions(pages=(1, 2)))
    assert "--pages works with pdf only" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (ConvertOptions(audio_format="ogg"), "unknown audio format"),
        (ConvertOptions(subtitle_formats=("ass",)), "unknown subtitle format"),
        (ConvertOptions(gap_ms=-1), "--gap-ms"),
        (ConvertOptions(max_chars=0), "--max-chars"),
    ],
)
def test_options_are_validated(options: ConvertOptions, message: str) -> None:
    with pytest.raises(ReaderError, match=message):
        options.validate()


def test_the_cache_makes_a_second_convert_free(tmp_path: Path,
                                               fake_engine: FakeEngine) -> None:
    source = write_source(tmp_path)
    options = ConvertOptions(cache_dir=tmp_path / "cache")
    convert(source, options)
    assert fake_engine.spoken == ["First line.", "Second line."]

    fake_engine.spoken = []
    convert(source, options)
    assert fake_engine.spoken == []


def test_no_cache_always_synthesizes(tmp_path: Path, fake_engine: FakeEngine) -> None:
    source = write_source(tmp_path)
    options = ConvertOptions(cache_dir=tmp_path / "cache", use_cache=False)
    convert(source, options)
    fake_engine.spoken = []
    convert(source, options)
    assert len(fake_engine.spoken) == 2


CHAPTERED = """# Opening

First words.

## Chapter One

It begins here.

## Chapter Two

It ends here.
"""


def write_book(tmp_path: Path) -> Path:
    path = tmp_path / "book.md"
    path.write_text(CHAPTERED, encoding="utf-8")
    return path


def test_headings_become_chapter_marks(tmp_path: Path, fake_engine: FakeEngine) -> None:
    result = convert(write_book(tmp_path), ConvertOptions(gap_ms=0))

    titles = [mark.title for mark in result.chapters]
    assert titles == ["Opening", "Chapter One", "Chapter Two"]
    # Six lines of two seconds each, three chapters of two lines.
    assert [mark.start for mark in result.chapters] == [0.0, 4.0, 8.0]
    assert result.chapters[-1].end == pytest.approx(12.0)
    assert WRITTEN_CHAPTERS and WRITTEN_CHAPTERS[0][0] == str(result.audio)


def test_no_chapters_leaves_the_tags_alone(tmp_path: Path,
                                           fake_engine: FakeEngine) -> None:
    result = convert(write_book(tmp_path), ConvertOptions(chapters=False))
    assert result.chapters == ()
    assert WRITTEN_CHAPTERS == []


def test_wav_gets_no_chapters(tmp_path: Path, fake_engine: FakeEngine) -> None:
    # WAV has nowhere to put them.
    result = convert(write_book(tmp_path), ConvertOptions(audio_format="wav"))
    assert result.chapters == ()
    assert WRITTEN_CHAPTERS == []


def test_a_document_without_headings_gets_no_chapters(tmp_path: Path,
                                                      fake_engine: FakeEngine) -> None:
    assert convert(write_source(tmp_path), ConvertOptions()).chapters == ()


def test_the_chapter_level_decides_how_many(tmp_path: Path,
                                            fake_engine: FakeEngine) -> None:
    # Only one level 1 heading, so there is nothing to divide.
    result = convert(write_book(tmp_path), ConvertOptions(chapter_level=1))
    assert result.chapters == ()

    source = tmp_path / "two.md"
    source.write_text("# One\n\nText.\n\n# Two\n\nMore.\n", encoding="utf-8")
    result = convert(source, ConvertOptions(chapter_level=1))
    assert [mark.title for mark in result.chapters] == ["One", "Two"]


def test_split_by_heading_writes_one_file_per_chapter(
    tmp_path: Path, fake_engine: FakeEngine
) -> None:
    results = convert_all(write_book(tmp_path), ConvertOptions(split_level=2))

    assert [result.audio.name for result in results] == [
        "book-01-Opening.mp3",
        "book-02-Chapter-One.mp3",
        "book-03-Chapter-Two.mp3",
    ]
    assert all(result.audio.exists() for result in results)
    assert [result.subtitle_files[0].name for result in results] == [
        "book-01-Opening.lrc",
        "book-02-Chapter-One.lrc",
        "book-03-Chapter-Two.lrc",
    ]
    # Each part covers its own lines only.
    assert results[1].texts == ("Chapter One", "It begins here.")


def test_without_splitting_convert_all_returns_one(tmp_path: Path,
                                                   fake_engine: FakeEngine) -> None:
    results = convert_all(write_book(tmp_path), ConvertOptions())
    assert len(results) == 1
    assert results[0].audio.name == "book.mp3"


@pytest.mark.parametrize("level", [0, 7])
def test_a_silly_heading_level_is_rejected(level: int) -> None:
    with pytest.raises(ReaderError, match="between 1 and 6"):
        ConvertOptions(split_level=level).validate()


def test_the_cache_is_kept_inside_its_limit(tmp_path: Path,
                                            fake_engine: FakeEngine) -> None:
    from iroha_reader_cli.cache import SegmentCache

    store = tmp_path / "cache"
    options = ConvertOptions(cache_dir=store, cache_max_mb=1)
    # Something big and old is already in there.
    old = tmp_path / "old.wav"
    old.write_bytes(b"x" * 2_000_000)
    cache = SegmentCache(store)
    cache.put("f" * 32, "wav", old)
    os.utime(cache.path_for("f" * 32, "wav"), (1_000_000, 1_000_000))

    convert(write_source(tmp_path), options)

    assert cache.get("f" * 32, "wav") is None


def test_pruning_can_be_turned_off(tmp_path: Path, fake_engine: FakeEngine) -> None:
    from iroha_reader_cli.cache import SegmentCache

    store = tmp_path / "cache"
    old = tmp_path / "old.wav"
    old.write_bytes(b"x" * 2_000_000)
    cache = SegmentCache(store)
    cache.put("f" * 32, "wav", old)

    convert(write_source(tmp_path), ConvertOptions(cache_dir=store, cache_max_mb=0))

    assert cache.get("f" * 32, "wav") is not None


def test_the_result_serializes_to_json(tmp_path: Path, fake_engine: FakeEngine) -> None:
    import json

    result = convert(write_book(tmp_path),
                     ConvertOptions(gap_ms=0, write_text=True,
                                    subtitle_formats=("lrc", "srt")))
    payload = result.as_dict()
    assert json.loads(json.dumps(payload)) == payload

    assert payload["engine"] == "fake"
    assert payload["audio"].endswith("book.mp3")
    assert [Path(p).name for p in payload["subtitles"]] == ["book.lrc", "book.srt"]
    assert payload["text_file"].endswith("book.lines.txt")
    assert payload["total"] == pytest.approx(12.0)
    assert [c["title"] for c in payload["chapters"]] == [
        "Opening", "Chapter One", "Chapter Two",
    ]
    first = payload["lines"][0]
    assert first == {"text": "Opening", "heading": 1, "start": 0.0, "end": 2.0}
    assert "words" not in first


def test_word_times_reach_the_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   fake_engine: FakeEngine) -> None:
    from iroha_reader_cli.timeline import Word

    def with_words(lines: Sequence[str], outdir: str,
                   reporter: Reporter) -> Segments:
        segments = FakeEngine.synth_all(fake_engine, lines, outdir, reporter)
        return Segments(segments.paths,
                        [[Word(line.split()[0], 0.0, 0.5)] for line in lines])

    # An engine that reports words has to say so; the cache checks it.
    monkeypatch.setattr(fake_engine, "word_timing", True)
    monkeypatch.setattr(fake_engine, "synth_all", with_words)
    payload = convert(write_source(tmp_path),
                      ConvertOptions(cache_dir=tmp_path / "cache")).as_dict()
    assert payload["lines"][0]["words"] == [
        {"text": "First", "start": 0.0, "end": 0.5},
    ]
