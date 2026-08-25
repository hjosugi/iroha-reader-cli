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
#: Seconds to wait after the nth failed try of one line.
RETRY_BACKOFF = 1.5
#: Consecutive line failures before the whole run slows down.
THROTTLE_AFTER = 3
#: Longest global pause, in seconds.
MAX_PAUSE = 30.0
#: The service reports offsets in 100 nanosecond ticks.
TICKS_PER_SECOND = 10_000_000

_THROTTLE_SIGNS = ("429", "too many requests", "throttl", "quota", "rate limit")


class EdgeEngine(Engine):
    """Online engine driven by the edge-tts package."""

    name = "edge"
    ext = "mp3"

    def __init__(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz",
                 volume: str = "+0%", concurrency: int = 4,
                 word_timing: bool = False, min_interval_ms: int = 0):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.concurrency = max(1, concurrency)
        # This engine is the only one that knows where each word falls:
        # the service sends a boundary event per word.
        self.word_timing = word_timing
        self.min_interval_ms = max(0, min_interval_ms)

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
        pace = _Pace(self.min_interval_ms / 1000.0)
        streak = _FailureStreak(reporter)
        words: list[list[Word]] = [[] for _ in lines]
        done = 0

        async def one(index: int, text: str) -> None:
            nonlocal done
            async with gate:
                last_err: Exception | None = None
                for attempt in range(RETRIES):
                    await streak.wait()
                    await pace.wait()
                    try:
                        words[index] = await self._speak(edge_tts, text, paths[index])
                        last_err = None
                        break
                    except Exception as err:  # the package raises many types
                        last_err = err
                        streak.failed()
                        # Back off, then retry. The service may be throttling us.
                        await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                if last_err is not None:
                    raise ReaderError(
                        f"edge tts failed on line {index + 1} after {RETRIES} tries: "
                        f"{last_err}\n{_advice(last_err)}"
                    ) from last_err
                streak.worked()
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


def _advice(err: Exception) -> str:
    """Say what to do about it, and name the cause when it is knowable."""
    text = str(err).lower()
    if any(sign in text for sign in _THROTTLE_SIGNS):
        return ("The service is throttling this account or address. Wait a while, "
                "lower --concurrency, raise --min-interval-ms, or use a local engine "
                "(--engine piper / openjtalk).")
    if "certificate" in text or "ssl" in text:
        return "That looks like a TLS problem, not a throttle. Check the system clock."
    if any(sign in text for sign in ("timed out", "timeout", "connect", "dns",
                                     "name resolution", "unreachable")):
        return ("That looks like a network problem, not a throttle. The edge engine "
                "needs the internet; the local engines do not.")
    return ("Retry later, lower --concurrency, or switch to a local engine. The edge "
            "engine is an unofficial use of an online service.")


class _Pace:
    """Keeps requests at least `interval` seconds apart."""

    def __init__(self, interval: float):
        self.interval = interval
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if self.interval <= 0:
            return
        async with self._lock:
            now = asyncio.get_running_loop().time()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            await asyncio.sleep(delay)


class _FailureStreak:
    """Slows the whole run down once failures stop looking like bad luck.

    Per line retries are not enough on their own: when the service
    starts refusing, every remaining line burns its tries at full
    speed and the run takes a long time to fail.
    """

    def __init__(self, reporter: Reporter):
        self.reporter = reporter
        self.count = 0
        self._warned = False

    def failed(self) -> None:
        self.count += 1

    def worked(self) -> None:
        self.count = 0

    async def wait(self) -> None:
        if self.count < THROTTLE_AFTER:
            return
        pause = min(MAX_PAUSE, 2.0 ** (self.count - THROTTLE_AFTER + 1))
        if not self._warned:
            self._warned = True
            self.reporter.warn(
                f"{self.count} failures in a row from the edge service. "
                f"Slowing down (up to {MAX_PAUSE:.0f}s between tries)."
            )
        await asyncio.sleep(pause)


async def list_voices() -> list[Any]:
    """Return every voice the service offers."""
    import edge_tts

    return list(await edge_tts.list_voices())
