"""Shared engine plumbing.

An engine turns a list of lines into one audio file per line. The
pipeline measures those files, so the timestamps always match the
audio it ships.
"""

from __future__ import annotations

import abc
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import ClassVar

from ..reporting import Reporter


class Engine(abc.ABC):
    """Base class for every TTS engine."""

    #: Name used by --engine and in log lines.
    name: ClassVar[str]
    #: Extension of the per-line files this engine writes.
    ext: ClassVar[str]

    @property
    def detail(self) -> str:
        """Voice or model shown next to the engine name. May be empty."""
        return ""

    @abc.abstractmethod
    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> list[str]:
        """Synthesize every line. Return the segment paths, in order."""

    def segment_paths(self, count: int, outdir: str) -> list[str]:
        return [str(Path(outdir) / f"seg_{i:05d}.{self.ext}") for i in range(count)]


class LocalEngine(Engine):
    """An engine that shells out once per line.

    Lines are independent, so they run in a small thread pool. The
    threads only wait on subprocesses, which is where the time goes.
    """

    def __init__(self, jobs: int = 1):
        self.jobs = max(1, jobs)

    @abc.abstractmethod
    def synth_one(self, text: str, path: str) -> None:
        """Write one line of speech to path."""

    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> list[str]:
        paths = self.segment_paths(len(lines), outdir)
        total = len(lines)
        done = 0
        lock = threading.Lock()

        def one(index: int) -> None:
            nonlocal done
            self.synth_one(lines[index], paths[index])
            with lock:
                done += 1
                reporter.progress(done, total)

        if self.jobs == 1 or total < 2:
            for i in range(total):
                one(i)
        else:
            with ThreadPoolExecutor(max_workers=self.jobs) as pool:
                # list() re-raises the first failure once the pool drains.
                list(pool.map(one, range(total)))
        reporter.progress_done()
        return paths
