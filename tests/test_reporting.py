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


class FakeTerminal(io.StringIO):
    """A stream that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


def test_a_terminal_gets_one_rewritten_line() -> None:
    stream = FakeTerminal()
    reporter = Reporter(stream=stream)
    reporter.progress(1, 2)
    reporter.progress(2, 2)
    reporter.info("done")
    assert stream.getvalue() == "\r  tts: 1/2\r  tts: 2/2\ndone\n"


def test_a_log_file_gets_a_handful_of_lines() -> None:
    stream = io.StringIO()
    reporter = Reporter(stream=stream)
    for done in range(1, 1001):
        reporter.progress(done, 1000)
    lines = stream.getvalue().splitlines()
    # Ten steps, not a thousand carriage returns.
    assert len(lines) == 10
    assert lines[0] == "  tts: 100/1000"
    assert lines[-1] == "  tts: 1000/1000"
    assert "\r" not in stream.getvalue()


def test_a_short_run_still_reports_every_line() -> None:
    stream = io.StringIO()
    reporter = Reporter(stream=stream)
    for done in (1, 2, 3):
        reporter.progress(done, 3)
    assert stream.getvalue().splitlines() == [
        "  tts: 1/3", "  tts: 2/3", "  tts: 3/3",
    ]
