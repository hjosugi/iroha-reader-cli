"""Text to subtitle lines."""

from __future__ import annotations

import pytest

from iroha_reader_cli.segment import has_japanese, segment, split_sentences, wrap


def test_has_japanese_detects_kana_and_kanji() -> None:
    assert has_japanese("これはテストです")
    assert has_japanese("日本語")
    assert not has_japanese("plain ascii 3.14")


def test_split_sentences_keeps_decimals_together() -> None:
    assert split_sentences("Pi is 3.14 here. And more.") == ["Pi is 3.14 here.", "And more."]


def test_split_sentences_handles_japanese_enders() -> None:
    assert split_sentences("これは一つ。これは二つ！三つ？") == [
        "これは一つ。", "これは二つ！", "三つ？",
    ]


def test_wrap_prefers_a_natural_break() -> None:
    line = "あいうえお、かきくけこさしすせそたちつてと"
    chunks = wrap(line, 10)
    assert chunks[0] == "あいうえお、"
    assert all(len(chunk) <= 10 for chunk in chunks)
    assert "".join(chunks) == line.replace("　", "")


def test_wrap_splits_even_without_a_break_point() -> None:
    assert wrap("あ" * 25, 10) == ["あ" * 10, "あ" * 10, "あ" * 5]


def test_segment_joins_wrapped_source_lines() -> None:
    text = "first line\ncontinues here.\n\nSecond paragraph."
    assert segment(text) == ["first line continues here.", "Second paragraph."]


def test_segment_drops_chunks_without_words() -> None:
    assert segment("Real text.\n\n---\n\n***") == ["Real text."]


def test_segment_rejects_a_bad_width() -> None:
    with pytest.raises(ValueError, match="max_chars"):
        segment("text", max_chars=0)


def test_only_the_first_line_of_a_heading_is_marked() -> None:
    from iroha_reader_cli.document import Block
    from iroha_reader_cli.segment import segment_blocks

    blocks = [Block("A very long heading that has to wrap somewhere", heading=2),
              Block("Body text.")]
    lines = segment_blocks(blocks, max_chars=20)
    assert lines[0].heading == 2
    assert [line.heading for line in lines[1:]] == [None] * (len(lines) - 1)
