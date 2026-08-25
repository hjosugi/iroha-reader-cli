"""The reading dictionary."""

from __future__ import annotations

from pathlib import Path

import pytest

from iroha_reader_cli.errors import ReaderError
from iroha_reader_cli.readings import Readings


def test_parse_skips_comments_and_blank_lines() -> None:
    readings = Readings.parse("# note\n\nIIJ\tアイアイジェイ\n")
    assert readings.rules == (("IIJ", "アイアイジェイ"),)
    assert readings


def test_longer_words_win() -> None:
    readings = Readings.parse("DB\tディービー\nDBA\tディービーエー\n")
    assert readings.apply("DBA and DB") == "ディービーエー and ディービー"


def test_apply_all_keeps_line_order() -> None:
    readings = Readings.parse("a\tb")
    assert readings.apply_all(["a1", "a2"]) == ["b1", "b2"]


def test_empty_dictionary_is_falsy() -> None:
    assert not Readings()
    assert Readings().apply("unchanged") == "unchanged"


def test_a_line_without_a_tab_is_an_error() -> None:
    with pytest.raises(ReaderError, match="word<TAB>reading"):
        Readings.parse("no tab here", source="d.tsv")


def test_load_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="not found"):
        Readings.load(tmp_path / "missing.tsv")


def test_load_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "d.tsv"
    path.write_text("DWH\tデータウェアハウス\n", encoding="utf-8")
    assert Readings.load(path).apply("DWH") == "データウェアハウス"
