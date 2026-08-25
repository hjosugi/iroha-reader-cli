"""LRC, SRT, and VTT rendering."""

from __future__ import annotations

import pytest

from iroha_reader_cli.subtitles import build_lrc, build_srt, build_vtt, render
from iroha_reader_cli.timeline import build

LINES = ["first line", "second line"]
TIMELINE = build([61.5, 2.0], gap_sec=0.5)


def test_lrc_has_a_header_and_one_stamp_per_line() -> None:
    text = build_lrc(LINES, TIMELINE, title="notes")
    assert text.startswith("[ti:notes]\n[re:iroha-reader-cli]\n[length:01:04.00]\n")
    assert "[00:00.00]first line" in text
    assert "[01:02.00]second line" in text
    assert text.endswith("\n")


def test_srt_numbers_cues_and_uses_comma_millis() -> None:
    text = build_srt(LINES, TIMELINE)
    assert text.splitlines()[:3] == [
        "1", "00:00:00,000 --> 00:01:01,500", "first line",
    ]
    assert "00:01:02,000 --> 00:01:04,000" in text


def test_vtt_starts_with_the_magic_line_and_uses_dot_millis() -> None:
    text = build_vtt(LINES, TIMELINE)
    assert text.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:01:01.500" in text


def test_render_dispatches_by_name() -> None:
    assert render("lrc", LINES, TIMELINE, "notes") == build_lrc(LINES, TIMELINE, "notes")
    with pytest.raises(ValueError, match="unknown subtitle format"):
        render("ass", LINES, TIMELINE)


def test_negative_times_clamp_to_zero() -> None:
    timeline = build([1.0], gap_sec=0.0)
    assert "[00:00.00]" in build_lrc(["x"], timeline)


def _word_timeline() -> tuple[list[str], object]:
    from iroha_reader_cli.timeline import Word, build

    lines = ["Hello there, world.", "Second line here."]
    timeline = build(
        [2.0, 2.0],
        gap_sec=0.0,
        words=[
            [Word("Hello", 0.0, 0.4), Word("there", 0.5, 0.4), Word("world", 1.0, 0.4)],
            [Word("Second", 0.0, 0.4), Word("line", 0.5, 0.4)],
        ],
    )
    return lines, timeline


def test_word_times_become_enhanced_lrc_tags() -> None:
    lines, timeline = _word_timeline()
    text = build_lrc(lines, timeline)  # type: ignore[arg-type]

    assert "[00:00.00]<00:00.00>Hello <00:00.50>there, <00:01.00>world." in text
    # The line start still comes first, and punctuation survives.
    assert "[00:02.00]<00:02.00>Second <00:02.50>line here." in text


def test_word_times_become_karaoke_vtt_cues() -> None:
    lines, timeline = _word_timeline()
    text = build_vtt(lines, timeline)  # type: ignore[arg-type]
    assert "<00:00:00.000>Hello <00:00:00.500>there, <00:00:01.000>world." in text


def test_a_word_the_engine_invented_is_skipped() -> None:
    from iroha_reader_cli.timeline import Word, build

    timeline = build([1.0], gap_sec=0.0,
                     words=[[Word("Hello", 0.0, 0.2), Word("nowhere", 0.5, 0.2)]])
    assert build_lrc(["Hello world."], timeline) .endswith(
        "[00:00.00]<00:00.00>Hello world.\n")
