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
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ..reporting import Reporter
from ..timeline import Word

__all__ = ["Engine", "LocalEngine", "Segments", "Word"]


@dataclass(frozen=True, slots=True)
class Segments:
    """What an engine produced: one file per line, and word times if it has them."""

    paths: list[str]
    #: Per line, in the same order as paths. None when the engine cannot
    #: report where each word falls.
    words: list[list[Word]] | None = field(default=None)


class Engine(abc.ABC):
    """Base class for every TTS engine."""

    #: Name used by --engine and in log lines. Set on the class.
    name: str
    #: Extension of the per-line files this engine writes. Set on the class.
    ext: str

    #: Attributes that change speed of work, not the sound of it.
    NON_AUDIO_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"jobs", "concurrency", "timeout", "name", "ext",
         "inner", "cache", "reused", "repeats"}
    )

    @property
    def detail(self) -> str:
        """Voice or model shown next to the engine name. May be empty."""
        return ""

    def signature(self) -> dict[str, str]:
        """Everything about this engine that can change how a line sounds.

        Used as the cache key, so a changed voice or speed misses on
        purpose. Values that name an existing file carry its size and
        mtime, because swapping a voice file keeps the path.
        """
        fields = {"engine": self.name}
        for key, value in sorted(vars(self).items()):
            if key in self.NON_AUDIO_FIELDS or key.startswith("_"):
                continue
            # Settings are scalars. Anything else is bookkeeping.
            if isinstance(value, str | int | float | bool | Path) or value is None:
                fields[key] = _describe(value)
        return fields

    #: True when this engine can say where each word starts.
    word_timing: bool = False

    @abc.abstractmethod
    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> Segments:
        """Synthesize every line, in order."""

    def segment_paths(self, count: int, outdir: str) -> list[str]:
        return [str(Path(outdir) / f"seg_{i:05d}.{self.ext}") for i in range(count)]


def _describe(value: object) -> str:
    """Render one setting for the signature, stamping files by content."""
    text = str(value)
    try:
        stat = Path(text).stat()
    except (OSError, ValueError):
        return text
    return f"{text}:{stat.st_size}:{int(stat.st_mtime)}"


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
                  reporter: Reporter) -> Segments:
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
        return Segments(paths)
