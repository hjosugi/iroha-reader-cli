"""Edge TTS: high quality voices over Microsoft's online service.

There is no charge, but this is an unofficial use of an online
service through the `edge-tts` package. It needs a network and may
throttle or break at any time, so it is opt-in only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from ..errors import ReaderError
from ..reporting import Reporter
from .base import Engine

DEFAULT_VOICE_JA = "ja-JP-NanamiNeural"
DEFAULT_VOICE_EN = "en-US-JennyNeural"

RETRIES = 3


class EdgeEngine(Engine):
    """Online engine driven by the edge-tts package."""

    name = "edge"
    ext = "mp3"

    def __init__(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz",
                 volume: str = "+0%", concurrency: int = 4):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.concurrency = max(1, concurrency)

    @property
    def detail(self) -> str:
        return self.voice

    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> list[str]:
        return asyncio.run(self._synth_all(lines, outdir, reporter))

    async def _synth_all(self, lines: Sequence[str], outdir: str,
                         reporter: Reporter) -> list[str]:
        try:
            import edge_tts
        except ImportError as err:  # pragma: no cover - dependency is required
            raise ReaderError(
                "the edge engine needs the edge-tts package: pip install edge-tts"
            ) from err

        paths = self.segment_paths(len(lines), outdir)
        total = len(lines)
        gate = asyncio.Semaphore(self.concurrency)
        done = 0

        async def one(index: int, text: str) -> None:
            nonlocal done
            async with gate:
                last_err: Exception | None = None
                for attempt in range(RETRIES):
                    try:
                        speech = edge_tts.Communicate(
                            text, self.voice, rate=self.rate,
                            pitch=self.pitch, volume=self.volume,
                        )
                        await speech.save(paths[index])
                        last_err = None
                        break
                    except Exception as err:  # the package raises many types
                        last_err = err
                        # Back off, then retry. The service may be throttling us.
                        await asyncio.sleep(1.5 * (attempt + 1))
                if last_err is not None:
                    raise ReaderError(
                        f"edge tts failed on line {index + 1} after {RETRIES} tries: "
                        f"{last_err}. The service throttles heavy use -- retry later, "
                        "lower --concurrency, or switch to a local engine."
                    ) from last_err
                done += 1
                reporter.progress(done, total)

        await asyncio.gather(*(one(i, text) for i, text in enumerate(lines)))
        reporter.progress_done()
        return paths


async def list_voices() -> list[Any]:
    """Return every voice the service offers."""
    import edge_tts

    return list(await edge_tts.list_voices())
