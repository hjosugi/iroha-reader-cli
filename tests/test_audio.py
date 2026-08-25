"""ffmpeg glue."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import requires_ffmpeg
from iroha_reader_cli import audio
from iroha_reader_cli.audio import ChapterMark, _ffmetadata
from iroha_reader_cli.errors import MissingCommandError
from iroha_reader_cli.proc import run


def test_ffmetadata_lists_the_chapters_in_milliseconds() -> None:
    text = _ffmetadata([ChapterMark("One", 0.0, 1.5), ChapterMark("Two", 1.5, 4.25)],
                       title="book")
    assert text.startswith(";FFMETADATA1\ntitle=book\n")
    assert "START=0\nEND=1500\ntitle=One" in text
    assert "START=1500\nEND=4250\ntitle=Two" in text


def test_ffmetadata_escapes_the_special_characters() -> None:
    text = _ffmetadata([ChapterMark("a=b;c#d", 0.0, 1.0)])
    assert r"title=a\=b\;c\#d" in text


def test_negative_times_clamp() -> None:
    assert "START=0" in _ffmetadata([ChapterMark("x", -2.0, 1.0)])


def test_check_tools_names_what_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    with pytest.raises(MissingCommandError, match="ffmpeg"):
        audio.check_tools()


def test_concat_needs_something_to_join() -> None:
    with pytest.raises(ValueError, match="at least one"):
        audio.concat([], "out.mp3")


@requires_ffmpeg
def test_silence_is_as_long_as_asked(tmp_path: Path) -> None:
    path = str(tmp_path / "quiet.wav")
    audio.make_silence(path, 500, 22050)
    assert audio.duration_sec(path) == pytest.approx(0.5, abs=0.02)
    assert audio.sample_rate(path) == 22050


@requires_ffmpeg
def test_a_path_with_a_quote_still_joins(tmp_path: Path) -> None:
    # The concat list format quotes with '', so a quote in the name has
    # to be escaped or ffmpeg reads the wrong file.
    awkward = tmp_path / "it's here.wav"
    audio.make_silence(str(awkward), 200, 22050)
    out = str(tmp_path / "joined.wav")
    audio.concat([str(awkward), str(awkward)], out)
    assert audio.duration_sec(out) == pytest.approx(0.4, abs=0.05)


@requires_ffmpeg
def test_chapters_land_in_the_mp3(tmp_path: Path) -> None:
    quiet = str(tmp_path / "quiet.wav")
    audio.make_silence(quiet, 1000, 22050)
    mp3 = str(tmp_path / "book.mp3")
    audio.concat([quiet, quiet], mp3)

    audio.write_chapters(mp3, [ChapterMark("One", 0.0, 1.0),
                               ChapterMark("Two", 1.0, 2.0)], title="book")
    out = run([
        "ffprobe", "-v", "error", "-show_chapters", "-of", "compact", mp3,
    ]).stdout.decode()
    assert "tag:title=One" in out
    assert "tag:title=Two" in out
    assert audio.duration_sec(mp3) == pytest.approx(2.0, abs=0.2)


@requires_ffmpeg
def test_wav_length_comes_from_the_header(tmp_path: Path) -> None:
    path = str(tmp_path / "quiet.wav")
    audio.make_silence(path, 1234, 22050)
    # The header answer has to match what ffprobe would have said.
    from_header = audio.wav_duration(path)
    assert from_header is not None
    assert from_header == pytest.approx(float(audio._probe(path, "format=duration")),
                                        abs=0.001)


def test_a_file_that_is_not_a_wav_falls_back(tmp_path: Path) -> None:
    path = tmp_path / "nope.wav"
    path.write_bytes(b"ID3 this is an mp3 really")
    assert audio.wav_duration(str(path)) is None


def test_a_missing_file_falls_back(tmp_path: Path) -> None:
    assert audio.wav_duration(str(tmp_path / "gone.wav")) is None


def test_a_truncated_wav_reports_what_is_there(tmp_path: Path) -> None:
    # 1 second at 8000 bytes per second, but only half the data is written.
    header = (b"RIFF" + (36 + 8000).to_bytes(4, "little") + b"WAVEfmt "
              + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
              + (1).to_bytes(2, "little") + (8000).to_bytes(4, "little")
              + (8000).to_bytes(4, "little") + (1).to_bytes(2, "little")
              + (8).to_bytes(2, "little")
              + b"data" + (8000).to_bytes(4, "little"))
    path = tmp_path / "half.wav"
    path.write_bytes(header + b"\x00" * 4000)
    assert audio.wav_duration(str(path)) == pytest.approx(0.5)


def test_an_odd_sized_chunk_is_skipped(tmp_path: Path) -> None:
    # LIST chunks with an odd length are padded to an even boundary.
    odd = b"LIST" + (3).to_bytes(4, "little") + b"abc" + b"\x00"
    header = (b"RIFF" + (0).to_bytes(4, "little") + b"WAVE" + odd + b"fmt "
              + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
              + (1).to_bytes(2, "little") + (8000).to_bytes(4, "little")
              + (16000).to_bytes(4, "little") + (2).to_bytes(2, "little")
              + (16).to_bytes(2, "little")
              + b"data" + (16000).to_bytes(4, "little"))
    path = tmp_path / "listed.wav"
    path.write_bytes(header + b"\x00" * 16000)
    assert audio.wav_duration(str(path)) == pytest.approx(1.0)
