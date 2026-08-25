"""The conversion itself, with the audio tools stubbed out."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from iroha_reader_cli import audio, pipeline
from iroha_reader_cli.engines.base import Engine
from iroha_reader_cli.errors import ReaderError
from iroha_reader_cli.pipeline import ConvertOptions, convert
from iroha_reader_cli.readings import Readings
from iroha_reader_cli.reporting import Reporter

SEGMENT_SEC = 2.0


class FakeEngine(Engine):
    """Records the spoken text and writes empty segment files."""

    name = "fake"
    ext = "wav"

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> list[str]:
        self.spoken = list(lines)
        paths = self.segment_paths(len(lines), outdir)
        for path in paths:
            Path(path).write_bytes(b"")
        reporter.progress_done()
        return paths


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
    assert result.lines == ("First line.", "Second line.")


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
    assert result.lines == ("DWH is here.",)
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
