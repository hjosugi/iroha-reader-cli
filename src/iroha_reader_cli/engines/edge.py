"""Edge TTS: high quality voices over Microsoft's online service.

There is no charge, but this is an unofficial use of an online
service through the `edge-tts` package. It needs a network and may
throttle or break at any time, so it is opt-in only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..errors import ReaderError
from ..reporting import Reporter
from .base import Engine, Segments, Word

DEFAULT_VOICE_JA = "ja-JP-NanamiNeural"
DEFAULT_VOICE_EN = "en-US-JennyNeural"

RETRIES = 3
#: The service reports offsets in 100 nanosecond ticks.
TICKS_PER_SECOND = 10_000_000


class EdgeEngine(Engine):
    """Online engine driven by the edge-tts package."""

    name = "edge"
    ext = "mp3"

    def __init__(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz",
                 volume: str = "+0%", concurrency: int = 4,
                 word_timing: bool = False):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.concurrency = max(1, concurrency)
        # This engine is the only one that knows where each word falls:
        # the service sends a boundary event per word.
        self.word_timing = word_timing

    @property
    def detail(self) -> str:
        return self.voice

    def synth_all(self, lines: Sequence[str], outdir: str,
                  reporter: Reporter) -> Segments:
        return asyncio.run(self._synth_all(lines, outdir, reporter))

    async def _synth_all(self, lines: Sequence[str], outdir: str,
                         reporter: Reporter) -> Segments:
        try:
            import edge_tts
        except ImportError as err:  # pragma: no cover - dependency is required
            raise ReaderError(
                "the edge engine needs the edge-tts package: pip install edge-tts"
            ) from err

        paths = self.segment_paths(len(lines), outdir)
        total = len(lines)
        gate = asyncio.Semaphore(self.concurrency)
        words: list[list[Word]] = [[] for _ in lines]
        done = 0

        async def one(index: int, text: str) -> None:
            nonlocal done
            async with gate:
                last_err: Exception | None = None
                for attempt in range(RETRIES):
                    try:
                        words[index] = await self._speak(edge_tts, text, paths[index])
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
        return Segments(paths, words if self.word_timing else None)

    async def _speak(self, edge_tts: Any, text: str, path: str) -> list[Word]:
        """Stream one line to disk, keeping the word boundaries on the way past."""
        speech = edge_tts.Communicate(
            text, self.voice, rate=self.rate, pitch=self.pitch, volume=self.volume,
            boundary="WordBoundary" if self.word_timing else "SentenceBoundary",
        )
        audio = bytearray()
        words: list[Word] = []
        async for chunk in speech.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                words.append(Word(
                    text=str(chunk["text"]),
                    start=int(chunk["offset"]) / TICKS_PER_SECOND,
                    duration=int(chunk["duration"]) / TICKS_PER_SECOND,
                ))
        if not audio:
            raise ReaderError("the edge service returned no audio")
        Path(path).write_bytes(bytes(audio))
        return words


async def list_voices() -> list[Any]:
    """Return every voice the service offers."""
    import edge_tts

    return list(await edge_tts.list_voices())
