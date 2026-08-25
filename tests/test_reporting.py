"""Status output."""

from __future__ import annotations

import io

from iroha_reader_cli.reporting import Reporter


def test_quiet_hides_info_and_progress() -> None:
    stream = io.StringIO()
    reporter = Reporter(quiet=True, stream=stream)
    reporter.info("hello")
    reporter.progress(1, 2)
    reporter.progress_done()
    assert stream.getvalue() == ""


def test_warnings_are_shown_even_when_quiet() -> None:
    stream = io.StringIO()
    Reporter(quiet=True, stream=stream).warn("careful")
    assert stream.getvalue() == "warning: careful\n"


def test_info_after_progress_starts_a_new_line() -> None:
    stream = io.StringIO()
    reporter = Reporter(stream=stream)
    reporter.progress(1, 2)
    reporter.info("done")
    assert stream.getvalue() == "\r  tts: 1/2\ndone\n"
