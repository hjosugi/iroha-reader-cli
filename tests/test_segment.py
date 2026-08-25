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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Dr. Smith went home. He slept.", ["Dr. Smith went home.", "He slept."]),
        ("J. R. R. Tolkien wrote it. Twice.",
         ["J. R. R. Tolkien wrote it.", "Twice."]),
        ("See fig. 3 for details. Then stop.",
         ["See fig. 3 for details.", "Then stop."]),
        ("Use e.g. this thing. Or that one.",
         ["Use e.g. this thing.", "Or that one."]),
        ("It cost 5 vs. 6 pounds. Cheap.", ["It cost 5 vs. 6 pounds.", "Cheap."]),
    ],
)
def test_an_abbreviation_does_not_end_a_sentence(text: str,
                                                 expected: list[str]) -> None:
    assert split_sentences(text) == expected


def test_a_real_sentence_end_still_ends_it() -> None:
    assert split_sentences("It ended. The end.") == ["It ended.", "The end."]


def test_a_closing_bracket_stays_with_its_sentence() -> None:
    assert split_sentences("「こんにちは。」と彼は言った。次の文です。") == [
        "「こんにちは。」", "と彼は言った。", "次の文です。",
    ]
    assert split_sentences('He said "stop." Then he left.') == [
        'He said "stop."', "Then he left.",
    ]


def test_a_lower_case_start_rejoins() -> None:
    # A sentence does not start in the middle of a word like this.
    assert split_sentences("Version 2. beta was released.") == [
        "Version 2. beta was released.",
    ]


def test_the_japanese_share_decides_the_voice() -> None:
    from iroha_reader_cli.segment import is_japanese, japanese_share

    english = "A paragraph of plain English prose, with nothing else in it."
    japanese = "これは日本語の文章です。読み上げは日本語の音声で行います。"
    quoted = english + ' The word for cat is "猫".'

    assert japanese_share(japanese) > 0.9
    assert is_japanese(japanese)

    # One quoted word is not a reason to read the whole page in Japanese.
    assert japanese_share(quoted) < 0.1
    assert not is_japanese(quoted)
    assert has_japanese(quoted)

    assert japanese_share(english) == 0.0
    assert not is_japanese(english)


def test_a_mixed_document_with_real_japanese_is_japanese() -> None:
    from iroha_reader_cli.segment import is_japanese

    mixed = "この記事では Python の subprocess モジュールについて説明します。"
    assert is_japanese(mixed)


def test_text_without_letters_is_not_japanese() -> None:
    from iroha_reader_cli.segment import japanese_share

    assert japanese_share("--- *** ...") == 0.0
