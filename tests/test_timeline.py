"""Segment lengths to timestamps."""

from __future__ import annotations

import pytest

from iroha_reader_cli.timeline import build


def test_starts_add_up_the_gaps() -> None:
    timeline = build([1.0, 2.0, 3.0], gap_sec=0.2)
    assert timeline.starts == pytest.approx((0.0, 1.2, 3.4))
    # Total is the audio plus the two gaps between the three segments.
    assert timeline.total == pytest.approx(6.4)


def test_no_gap_means_back_to_back() -> None:
    timeline = build([1.0, 2.0], gap_sec=0.0)
    assert timeline.starts == (0.0, 1.0)
    assert timeline.total == pytest.approx(3.0)


def test_empty_input_has_no_length() -> None:
    timeline = build([], gap_sec=0.2)
    assert timeline.starts == ()
    assert timeline.total == 0.0


def test_negative_gap_is_rejected() -> None:
    with pytest.raises(ValueError, match="gap_sec"):
        build([1.0], gap_sec=-0.1)
