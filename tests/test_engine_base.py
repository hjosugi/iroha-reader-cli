"""The shared local-engine plumbing."""

from __future__ import annotations

import io
import threading
from pathlib import Path

import pytest

from iroha_reader_cli.engines.base import LocalEngine
from iroha_reader_cli.reporting import Reporter


class CountingEngine(LocalEngine):
    name = "counting"
    ext = "wav"

    def __init__(self, jobs: int) -> None:
        super().__init__(jobs=jobs)
        self.seen: list[str] = []
        self.lock = threading.Lock()

    def synth_one(self, text: str, path: str) -> None:
        with self.lock:
            self.seen.append(text)
        Path(path).write_text(text, encoding="utf-8")


def test_segments_keep_their_order_when_parallel(tmp_path: Path) -> None:
    lines = [f"line {i}" for i in range(12)]
    engine = CountingEngine(jobs=4)
    paths = engine.synth_all(lines, str(tmp_path), Reporter(quiet=True))

    assert len(paths) == len(lines)
    assert sorted(engine.seen) == sorted(lines)
    assert [Path(p).read_text(encoding="utf-8") for p in paths] == lines


def test_one_job_still_works(tmp_path: Path) -> None:
    engine = CountingEngine(jobs=1)
    paths = engine.synth_all(["only"], str(tmp_path), Reporter(quiet=True))
    assert Path(paths[0]).name == "seg_00000.wav"


def test_progress_counts_every_line(tmp_path: Path) -> None:
    stream = io.StringIO()
    engine = CountingEngine(jobs=2)
    engine.synth_all(["a", "b", "c"], str(tmp_path), Reporter(stream=stream))
    assert stream.getvalue().count("tts: ") == 3
    assert stream.getvalue().endswith("\n")


def test_a_failing_line_stops_the_run(tmp_path: Path) -> None:
    class Broken(CountingEngine):
        def synth_one(self, text: str, path: str) -> None:
            if text == "b":
                raise RuntimeError("boom")
            super().synth_one(text, path)

    with pytest.raises(RuntimeError, match="boom"):
        Broken(jobs=3).synth_all(["a", "b", "c"], str(tmp_path), Reporter(quiet=True))
