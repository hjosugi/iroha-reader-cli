"""Shared test helpers."""

from __future__ import annotations

import shutil

import pytest


def _have(*commands: str) -> bool:
    return all(shutil.which(c) is not None for c in commands)


requires_ffmpeg = pytest.mark.skipif(
    not _have("ffmpeg", "ffprobe"), reason="needs ffmpeg and ffprobe"
)
requires_espeak = pytest.mark.skipif(
    not _have("espeak-ng"), reason="needs espeak-ng"
)
