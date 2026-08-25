"""A real conversion, end to end, with espeak-ng and ffmpeg.

This is the test that proves the promise of the tool: the last
timestamp really is inside the audio file it ships with.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import requires_espeak, requires_ffmpeg
from iroha_reader_cli import audio
from iroha_reader_cli.engines import EngineSettings
from iroha_reader_cli.pipeline import ConvertOptions, convert

TEXT = """# Sample

First sentence here. Second sentence follows.

Third one closes the file.
"""

pytestmark = [pytest.mark.slow, requires_ffmpeg, requires_espeak]


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "notes.md"
    path.write_text(TEXT, encoding="utf-8")
    return path


def test_conversion_produces_audio_that_matches_the_timeline(source: Path) -> None:
    result = convert(
        source,
        ConvertOptions(audio_format="wav", subtitle_formats=("lrc", "srt", "vtt"),
                       gap_ms=100),
        EngineSettings(requested="espeak", jobs=2),
    )

    assert result.engine == "espeak"
    assert result.audio.stat().st_size > 0
    measured = audio.duration_sec(str(result.audio))
    # The joined file is the sum of the segments plus the gaps.
    assert measured == pytest.approx(result.timeline.total, abs=0.25)

    lrc = result.subtitle_files[0].read_text(encoding="utf-8")
    assert "[length:" in lrc
    stamps = re.findall(r"^\[(\d\d):(\d\d\.\d\d)\]", lrc, flags=re.M)
    assert len(stamps) == len(result.lines)
    last = int(stamps[-1][0]) * 60 + float(stamps[-1][1])
    assert last < measured


def test_a_second_run_overwrites_cleanly(source: Path) -> None:
    settings = EngineSettings(requested="espeak")
    options = ConvertOptions(audio_format="wav")
    first = convert(source, options, settings)
    second = convert(source, options, settings)
    assert first.audio == second.audio
    assert second.audio.stat().st_size > 0


def test_the_reading_dictionary_reaches_the_engine(source: Path, tmp_path: Path) -> None:
    from iroha_reader_cli.readings import Readings

    plain = convert(source, ConvertOptions(audio_format="wav", outdir=tmp_path / "a"),
                    EngineSettings(requested="espeak"))
    swapped = convert(
        source,
        ConvertOptions(audio_format="wav", outdir=tmp_path / "b",
                       readings=Readings.parse("sentence\tsupercalifragilistic")),
        EngineSettings(requested="espeak"),
    )
    # The longer spoken word makes the audio longer, but the text is untouched.
    assert swapped.timeline.total > plain.timeline.total
    assert swapped.lines == plain.lines
