"""Shared test helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never touch the developer's real segment cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def _have(*commands: str) -> bool:
    return all(shutil.which(c) is not None for c in commands)


requires_ffmpeg = pytest.mark.skipif(
    not _have("ffmpeg", "ffprobe"), reason="needs ffmpeg and ffprobe"
)
requires_espeak = pytest.mark.skipif(
    not _have("espeak-ng"), reason="needs espeak-ng"
)
