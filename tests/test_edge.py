"""The edge engine, against a fake service."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from iroha_reader_cli.engines import edge
from iroha_reader_cli.engines.edge import TICKS_PER_SECOND, EdgeEngine
from iroha_reader_cli.errors import ReaderError
from iroha_reader_cli.reporting import Reporter

CALLS: list[dict[str, Any]] = []


class FakeCommunicate:
    """Speaks one tick per word and hands back a little audio."""

    def __init__(self, text: str, voice: str, **options: Any) -> None:
        self.text = text
        CALLS.append({"text": text, "voice": voice, **options})

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "audio", "data": b"MP3"}
        for index, word in enumerate(self.text.split()):
            yield {
                "type": "WordBoundary",
                "offset": index * TICKS_PER_SECOND // 2,
                "duration": TICKS_PER_SECOND // 4,
                "text": word.strip(".,"),
            }
        yield {"type": "audio", "data": b"DATA"}


@pytest.fixture(autouse=True)
def fake_edge_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    CALLS.clear()
    module = ModuleType("edge_tts")
    module.Communicate = FakeCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", module)


def test_word_boundaries_become_seconds(tmp_path: Path) -> None:
    engine = EdgeEngine("en-US-JennyNeural", word_timing=True)
    segments = engine.synth_all(["Hello there, world."], str(tmp_path),
                                Reporter(quiet=True))

    assert segments.words is not None
    words = segments.words[0]
    assert [word.text for word in words] == ["Hello", "there", "world"]
    assert [word.start for word in words] == [0.0, 0.5, 1.0]
    assert words[0].duration == 0.25
    assert Path(segments.paths[0]).read_bytes() == b"MP3DATA"


def test_word_timing_is_asked_for_only_when_wanted(tmp_path: Path) -> None:
    EdgeEngine("v", word_timing=True).synth_all(["one two"], str(tmp_path),
                                                Reporter(quiet=True))
    assert CALLS[0]["boundary"] == "WordBoundary"

    CALLS.clear()
    segments = EdgeEngine("v").synth_all(["one two"], str(tmp_path),
                                         Reporter(quiet=True))
    assert CALLS[0]["boundary"] == "SentenceBoundary"
    assert segments.words is None


def test_the_voice_settings_reach_the_service(tmp_path: Path) -> None:
    EdgeEngine("ja-JP-NanamiNeural", rate="+10%", pitch="-20Hz",
               volume="+5%").synth_all(["x"], str(tmp_path), Reporter(quiet=True))
    assert CALLS[0]["voice"] == "ja-JP-NanamiNeural"
    assert (CALLS[0]["rate"], CALLS[0]["pitch"], CALLS[0]["volume"]) == (
        "+10%", "-20Hz", "+5%")


def test_silence_from_the_service_is_an_error(tmp_path: Path) -> None:
    class Empty(FakeCommunicate):
        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            nothing: list[dict[str, Any]] = []
            for chunk in nothing:  # an async generator that yields nothing
                yield chunk

    engine = EdgeEngine("v")
    module = SimpleNamespace(Communicate=Empty)
    with pytest.raises(ReaderError, match="no audio"):
        asyncio.run(engine._speak(module, "hello", str(tmp_path / "a.mp3")))


def test_lines_keep_their_order(tmp_path: Path) -> None:
    lines = [f"line {index}" for index in range(6)]
    segments = EdgeEngine("v", concurrency=3, word_timing=True).synth_all(
        lines, str(tmp_path), Reporter(quiet=True)
    )
    assert segments.words is not None
    assert [words[1].text for words in segments.words] == [str(i) for i in range(6)]


class Flaky(FakeCommunicate):
    """Fails a set number of times, then behaves."""

    failures = 0

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        if Flaky.failures > 0:
            Flaky.failures -= 1
            raise RuntimeError("Too Many Requests (429)")
        async for chunk in super().stream():
            yield chunk


@pytest.fixture
def instant_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real waiting in the tests."""
    monkeypatch.setattr(edge, "RETRY_BACKOFF", 0.0)
    monkeypatch.setattr(edge, "MAX_PAUSE", 0.0)


def test_a_line_that_fails_once_is_retried(tmp_path: Path, instant_retries: None,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    Flaky.failures = 1
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Flaky))
    segments = EdgeEngine("v").synth_all(["hello"], str(tmp_path), Reporter(quiet=True))
    assert Path(segments.paths[0]).read_bytes() == b"MP3DATA"


def test_a_throttled_run_says_what_to_do(tmp_path: Path, instant_retries: None,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    Flaky.failures = 99
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Flaky))
    with pytest.raises(ReaderError, match="throttling this account"):
        EdgeEngine("v").synth_all(["hello"], str(tmp_path), Reporter(quiet=True))


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("HTTP 429 Too Many Requests", "throttling this account"),
        ("Cannot connect to host: name resolution failed", "network problem"),
        ("certificate verify failed", "TLS problem"),
        ("something else entirely", "Retry later"),
    ],
)
def test_the_advice_names_the_cause(message: str, expected: str) -> None:
    assert expected in edge._advice(RuntimeError(message))


def test_the_run_slows_down_after_a_streak(capsys: pytest.CaptureFixture[str]) -> None:
    streak = edge._FailureStreak(Reporter())
    for _ in range(edge.THROTTLE_AFTER):
        streak.failed()
    asyncio.run(streak.wait())
    assert "failures in a row" in capsys.readouterr().err
    streak.worked()
    assert streak.count == 0


def test_min_interval_spaces_requests_out(tmp_path: Path) -> None:
    engine = EdgeEngine("v", concurrency=4, min_interval_ms=40)
    lines = [f"line {index}" for index in range(4)]

    async def run() -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        await engine._synth_all(lines, str(tmp_path), Reporter(quiet=True))
        return loop.time() - started

    # Four requests, 40 ms apart, is at least 120 ms even in parallel.
    assert asyncio.run(run()) >= 0.12
