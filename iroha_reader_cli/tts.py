"""TTS engines. Each engine turns lines into audio segment files."""

import asyncio
import json
import os
import subprocess
import sys

QUIET = False


def _progress(done: int, total: int) -> None:
    if not QUIET:
        print(f"\r  tts: {done}/{total}", end="", file=sys.stderr)


def _progress_end() -> None:
    if not QUIET:
        print(file=sys.stderr)


class EdgeEngine:
    """Online engine. Uses Microsoft Edge TTS via the edge-tts package.

    Good quality. Needs network. Heavy use may get throttled.
    """

    ext = "mp3"
    name = "edge"

    def __init__(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz",
                 volume: str = "+0%", concurrency: int = 4):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.concurrency = concurrency

    def synth_all(self, lines: list[str], outdir: str) -> list[str]:
        return asyncio.run(self._run(lines, outdir))

    async def _run(self, lines: list[str], outdir: str) -> list[str]:
        import edge_tts

        sem = asyncio.Semaphore(self.concurrency)
        paths = [os.path.join(outdir, f"seg_{i:05d}.mp3") for i in range(len(lines))]
        done = 0

        async def one(i: int, text: str) -> None:
            nonlocal done
            async with sem:
                last_err: Exception | None = None
                for attempt in range(3):
                    try:
                        com = edge_tts.Communicate(
                            text, self.voice, rate=self.rate,
                            pitch=self.pitch, volume=self.volume,
                        )
                        await com.save(paths[i])
                        last_err = None
                        break
                    except Exception as err:  # noqa: BLE001
                        last_err = err
                        # Wait, then retry. The service may throttle us.
                        await asyncio.sleep(1.5 * (attempt + 1))
                if last_err is not None:
                    raise last_err
                done += 1
                _progress(done, len(lines))

        await asyncio.gather(*(one(i, t) for i, t in enumerate(lines)))
        _progress_end()
        return paths


class EspeakEngine:
    """Offline engine. Uses the espeak-ng command.

    Works with no network. Voice quality is basic.
    """

    ext = "wav"
    name = "espeak"

    def __init__(self, lang: str = "ja", wpm: int = 175,
                 pitch: int | None = None, amplitude: int | None = None):
        self.lang = lang
        self.wpm = wpm
        self.pitch = pitch
        self.amplitude = amplitude

    def synth_all(self, lines: list[str], outdir: str) -> list[str]:
        paths: list[str] = []
        for i, text in enumerate(lines):
            path = os.path.join(outdir, f"seg_{i:05d}.wav")
            cmd = [
                "espeak-ng",
                "-v", self.lang,
                "-s", str(self.wpm),
            ]
            if self.pitch is not None:
                cmd += ["-p", str(self.pitch)]
            if self.amplitude is not None:
                cmd += ["-a", str(self.amplitude)]
            cmd += ["-w", path, "--stdin"]
            # Send text on stdin. This is safe for any content.
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            paths.append(path)
            _progress(i + 1, len(lines))
        _progress_end()
        return paths


class OpenJTalkEngine:
    """Offline Japanese engine. Uses the open_jtalk command.

    Fully free and open source. Better Japanese quality than espeak.
    """

    ext = "wav"
    name = "openjtalk"

    def __init__(self, dict_dir: str, voice: str, speed: float = 1.0,
                 halftone: float = 0.0, volume_db: float = 0.0):
        self.dict_dir = dict_dir
        self.voice = voice
        self.speed = speed
        self.halftone = halftone
        self.volume_db = volume_db

    def synth_all(self, lines: list[str], outdir: str) -> list[str]:
        paths: list[str] = []
        for i, text in enumerate(lines):
            path = os.path.join(outdir, f"seg_{i:05d}.wav")
            cmd = [
                "open_jtalk",
                "-x", self.dict_dir,
                "-m", self.voice,
                "-r", str(self.speed),
                "-fm", str(self.halftone),
                "-g", str(self.volume_db),
                "-ow", path,
            ]
            # Send text on stdin. This is safe for any content.
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            paths.append(path)
            _progress(i + 1, len(lines))
        _progress_end()
        return paths


class VoicevoxEngine:
    """Local server engine. Talks to a running VOICEVOX engine over HTTP.

    VOICEVOX is free. Start the engine app first. Default port is 50021.
    Publishing the audio needs a credit line. Check the VOICEVOX terms.
    """

    ext = "wav"
    name = "voicevox"

    def __init__(self, url: str = "http://127.0.0.1:50021",
                 speaker: int = 3, speed: float = 1.0, pitch: float = 0.0,
                 intonation: float = 1.0, volume: float = 1.0,
                 timeout: int = 120):
        self.base = url.rstrip("/")
        self.speaker = speaker
        self.speed = speed
        self.pitch = pitch
        self.intonation = intonation
        self.volume = volume
        self.timeout = timeout

    @staticmethod
    def fetch_speakers(url: str, timeout: int = 10) -> list:
        """GET /speakers from a running engine. Exit with help on failure."""
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/speakers",
                                        timeout=timeout) as res:
                return json.loads(res.read())
        except urllib.error.URLError as err:
            raise SystemExit(
                f"error: cannot reach the VOICEVOX engine at {url}. "
                f"Start the engine and retry. ({err})"
            ) from err

    def _post(self, path_and_query: str, body: bytes | None,
              content_type: str | None) -> bytes:
        import urllib.error
        import urllib.request

        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(
            f"{self.base}{path_and_query}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return res.read()
        except urllib.error.URLError as err:
            raise SystemExit(
                f"error: cannot reach the VOICEVOX engine at {self.base}. "
                "Start the engine and retry. "
                f"({err})"
            ) from err

    def synth_all(self, lines: list[str], outdir: str) -> list[str]:
        import urllib.parse

        paths: list[str] = []
        for i, text in enumerate(lines):
            path = os.path.join(outdir, f"seg_{i:05d}.wav")
            # Step 1: build the audio query from the text.
            q = urllib.parse.urlencode({"speaker": self.speaker, "text": text})
            query_json = self._post(f"/audio_query?{q}", None, None)
            # Step 2: apply the voice settings to the query.
            query = json.loads(query_json)
            query["speedScale"] = self.speed
            query["pitchScale"] = self.pitch
            query["intonationScale"] = self.intonation
            query["volumeScale"] = self.volume
            query_json = json.dumps(query).encode("utf-8")
            # Step 3: turn the query into wav bytes.
            wav = self._post(
                f"/synthesis?speaker={self.speaker}",
                query_json,
                "application/json",
            )
            with open(path, "wb") as f:
                f.write(wav)
            paths.append(path)
            _progress(i + 1, len(lines))
        _progress_end()
        return paths


class PiperEngine:
    """Offline neural engine. Uses the piper command.

    High quality and fully local. Piper is a separate GPL-3.0 project.
    Install it with: pip install piper-tts
    Get voices with: python3 -m piper.download_voices <name>
    """

    ext = "wav"
    name = "piper"

    def __init__(self, model: str, length_scale: float = 1.0):
        self.model = model
        self.length_scale = length_scale

    def synth_all(self, lines: list[str], outdir: str) -> list[str]:
        paths: list[str] = []
        for i, text in enumerate(lines):
            path = os.path.join(outdir, f"seg_{i:05d}.wav")
            # Send text on stdin. This is safe for any content.
            subprocess.run(
                [
                    "piper",
                    "-m", self.model,
                    "-f", path,
                    "--length-scale", str(self.length_scale),
                ],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            paths.append(path)
            _progress(i + 1, len(lines))
        _progress_end()
        return paths
