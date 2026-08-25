"""Cache the synthesized segments.

Synthesis is the slow part; everything else is a few ffmpeg calls.
Editing one paragraph of a long document should not re-synthesize the
whole thing, so each line is stored under a hash of the text and every
engine setting that can change how it sounds.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .engines.base import Engine, Segments
from .reporting import Reporter
from .timeline import Word

APP_NAME = "iroha-reader-cli"
#: Cache size the CLI keeps to by default. 0 means no limit.
DEFAULT_MAX_MB = 2048


def default_dir() -> Path:
    """Return ~/.cache/iroha-reader-cli/segments (XDG aware)."""
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path("~/.cache").expanduser()
    return root / APP_NAME / "segments"


def key_for(signature: Mapping[str, Any], text: str) -> str:
    """Hash one line together with the settings that shape it."""
    payload = json.dumps({"signature": dict(signature), "text": text},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class SegmentCache:
    """A content addressed store of single-line audio files."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else default_dir()

    def path_for(self, key: str, ext: str) -> Path:
        # Two hex characters of fan-out keep the directories browsable.
        return self.root / key[:2] / f"{key}.{ext}"

    def get(self, key: str, ext: str) -> Path | None:
        path = self.path_for(key, ext)
        if not path.is_file():
            return None
        # Touch it so pruning keeps what is actually being used.
        with contextlib.suppress(OSError):
            os.utime(path)
        return path

    def get_words(self, key: str) -> list[Word] | None:
        """Read the word timings stored beside a segment, if any."""
        path = self.path_for(key, "json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [Word(**item) for item in data]
        except (OSError, ValueError, TypeError):
            return None

    def put(self, key: str, ext: str, source: Path,
            words: Sequence[Word] | None = None) -> None:
        """Store a segment, and its word timings when the engine has them.

        A failure here is never fatal: the cache is an optimisation.
        """
        try:
            self._store(self.path_for(key, ext), source.read_bytes())
            if words is not None:
                payload = json.dumps([asdict(word) for word in words],
                                     ensure_ascii=False)
                self._store(self.path_for(key, "json"), payload.encode("utf-8"))
        except OSError:
            return

    def _store(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_suffix(path.suffix + f".{os.getpid()}.part")
        staged.write_bytes(payload)
        staged.replace(path)  # atomic, so a reader never sees half a file

    def entries(self) -> list[tuple[float, int, Path]]:
        """Every cached file as (mtime, size, path), oldest first."""
        found: list[tuple[float, int, Path]] = []
        if not self.root.is_dir():
            return found
        for path in self.root.rglob("*"):
            try:
                if path.is_file():
                    stat = path.stat()
                    found.append((stat.st_mtime, stat.st_size, path))
            except OSError:
                continue
        found.sort()
        return found

    def prune(self, max_bytes: int) -> tuple[int, int]:
        """Drop the least recently used files until the cache fits.

        Returns (files removed, bytes freed). A cap of 0 or less means
        no limit, and nothing is touched.
        """
        if max_bytes <= 0:
            return (0, 0)
        found = self.entries()
        total = sum(size for _mtime, size, _path in found)
        removed = 0
        freed = 0
        for _mtime, _size, path in found:
            if total <= max_bytes:
                break
            # The word timings live beside their segment; drop both.
            for victim in (path, path.with_suffix(".json")):
                try:
                    gone = victim.stat().st_size
                    victim.unlink()
                except OSError:
                    continue
                total -= gone
                freed += gone
                removed += 1
        return removed, freed

    def clear(self) -> tuple[int, int]:
        """Delete everything. Returns (files removed, bytes freed)."""
        files = 0
        freed = 0
        if not self.root.is_dir():
            return (0, 0)
        for path in self.root.rglob("*"):
            if path.is_file():
                freed += path.stat().st_size
                path.unlink(missing_ok=True)
                files += 1
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        return files, freed


class CachedEngine(Engine):
    """Wraps an engine so repeated lines are only ever spoken once."""

    def __init__(self, inner: Engine, cache: SegmentCache):
        self.inner = inner
        self.cache = cache
        self.name = inner.name
        self.ext = inner.ext
        self.reused = 0
        self.repeats = 0

    @property
    def detail(self) -> str:
        return self.inner.detail

    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> Segments:
        signature = self.inner.signature()
        keys = [key_for(signature, line) for line in lines]
        paths = self.segment_paths(len(lines), outdir)
        # An entry without word timings is a miss when we need them.
        words: list[list[Word]] | None = (
            [[] for _ in lines] if self.inner.word_timing else None
        )

        missing: list[int] = []
        for index, key in enumerate(keys):
            hit = self.cache.get(key, self.ext)
            stored = self.cache.get_words(key) if words is not None else None
            if hit is None or (words is not None and stored is None):
                missing.append(index)
                continue
            try:
                shutil.copyfile(hit, paths[index])
            except OSError:
                missing.append(index)
                continue
            if words is not None and stored is not None:
                words[index] = stored

        self.reused = len(lines) - len(missing)
        if self.reused:
            reporter.info(f"  cache: {self.reused}/{len(lines)} lines reused")
        if not missing:
            return Segments(paths, words)

        # A line that appears twice in the document is one key, so it is
        # spoken once even on the very first run.
        by_key: dict[str, list[int]] = {}
        for index in missing:
            by_key.setdefault(keys[index], []).append(index)
        self.repeats = len(missing) - len(by_key)
        if self.repeats:
            reporter.info(f"  repeats: {self.repeats} lines spoken once")

        fresh_dir = Path(outdir) / "fresh"
        fresh_dir.mkdir(exist_ok=True)
        first_of = [targets[0] for targets in by_key.values()]
        fresh = self.inner.synth_all([lines[i] for i in first_of], str(fresh_dir),
                                     reporter)
        for position, ((key, targets), source) in enumerate(
                zip(by_key.items(), fresh.paths, strict=True)):
            head = targets[0]
            Path(source).replace(paths[head])
            spoken = fresh.words[position] if fresh.words is not None else None
            if words is not None and spoken is not None:
                for target in targets:
                    words[target] = spoken
            self.cache.put(key, self.ext, Path(paths[head]), spoken)
            for other in targets[1:]:
                shutil.copyfile(paths[head], paths[other])
        return Segments(paths, words)
