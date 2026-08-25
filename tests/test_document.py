"""Grouping lines into chapters."""

from __future__ import annotations

from iroha_reader_cli.document import Line, chapters, slug, texts

LINES = [
    Line("Front matter."),
    Line("Chapter One", heading=1),
    Line("It begins."),
    Line("A part of it", heading=2),
    Line("More."),
    Line("Chapter Two", heading=1),
    Line("It ends."),
]


def test_chapters_split_at_headings_of_that_level() -> None:
    parts = chapters(LINES, level=1)
    assert [part.title for part in parts] == ["", "Chapter One", "Chapter Two"]
    assert texts(parts[1].lines) == ["Chapter One", "It begins.", "A part of it", "More."]


def test_a_deeper_level_makes_more_chapters() -> None:
    parts = chapters(LINES, level=2)
    assert [part.title for part in parts] == [
        "", "Chapter One", "A part of it", "Chapter Two",
    ]


def test_the_opening_run_keeps_the_document_title() -> None:
    parts = chapters(LINES, level=1, title="notes")
    assert parts[0].title == "notes"
    assert texts(parts[0].lines) == ["Front matter."]


def test_chapters_cover_every_line() -> None:
    parts = chapters(LINES, level=2)
    assert sum(len(part.lines) for part in parts) == len(LINES)
    assert [part.start for part in parts] == [0, 1, 3, 5]
    assert parts[1].stop == 3


def test_a_document_without_headings_is_one_chapter() -> None:
    parts = chapters([Line("Just text."), Line("More text.")], level=1, title="doc")
    assert len(parts) == 1
    assert parts[0].title == "doc"


def test_no_lines_means_no_chapters() -> None:
    assert chapters([], level=1) == []


def test_slugs_are_file_name_safe() -> None:
    assert slug("Chapter One: the beginning") == "Chapter-One-the-beginning"
    assert slug("第一章 出会い") == "第一章-出会い"
    assert slug("///", fallback="part3") == "part3"
    assert len(slug("word " * 40)) <= 40
