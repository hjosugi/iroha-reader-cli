"""Cache the synthesized segments.

Synthesis is the slow part; everything else is a few ffmpeg calls.
Editing one paragraph of a long document should not re-synthesize the
whole thing, so each line is stored under a hash of the text and every
engine setting that can change how it sounds.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .engines.base import Engine
from .reporting import Reporter

APP_NAME = "iroha-reader-cli"


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
        return path if path.is_file() else None

    def put(self, key: str, ext: str, source: Path) -> None:
        """Store a segment. A failure here is never fatal."""
        path = self.path_for(key, ext)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            staged = path.with_suffix(path.suffix + f".{os.getpid()}.part")
            shutil.copyfile(source, staged)
            staged.replace(path)  # atomic, so a reader never sees half a file
        except OSError:
            return

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
                  reporter: Reporter) -> list[str]:
        signature = self.inner.signature()
        keys = [key_for(signature, line) for line in lines]
        paths = self.segment_paths(len(lines), outdir)

        missing: list[int] = []
        for index, key in enumerate(keys):
            hit = self.cache.get(key, self.ext)
            if hit is None:
                missing.append(index)
                continue
            try:
                shutil.copyfile(hit, paths[index])
            except OSError:
                missing.append(index)

        self.reused = len(lines) - len(missing)
        if self.reused:
            reporter.info(f"  cache: {self.reused}/{len(lines)} lines reused")
        if not missing:
            return paths

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
        for (key, targets), source in zip(by_key.items(), fresh, strict=True):
            head = targets[0]
            Path(source).replace(paths[head])
            self.cache.put(key, self.ext, Path(paths[head]))
            for other in targets[1:]:
                shutil.copyfile(paths[head], paths[other])
        return paths
