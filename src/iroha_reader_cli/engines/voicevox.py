"""VOICEVOX: high quality Japanese from a local HTTP engine.

VOICEVOX is free of charge. Start the engine app first (default port
50021). Published audio needs a credit line such as
`VOICEVOX:ずんだもん` -- check the terms of the character you use.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..errors import EngineNotReadyError, ReaderError
from .base import LocalEngine

DEFAULT_URL = "http://127.0.0.1:50021"
DEFAULT_SPEAKER = "3"


def _unreachable(url: str, err: Exception) -> ReaderError:
    return EngineNotReadyError(
        f"cannot reach the VOICEVOX engine at {url}. "
        f"Start the engine and retry. ({err})"
    )


def fetch_speakers(url: str, timeout: int = 10) -> list[dict[str, Any]]:
    """GET /speakers from a running engine."""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/speakers", timeout=timeout) as res:
            data = json.loads(res.read())
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise _unreachable(url, err) from err
    if not isinstance(data, list):
        raise EngineNotReadyError(f"unexpected /speakers response from {url}")
    return data


def resolve_speaker(spec: str, url: str) -> int:
    """Turn a style id, a speaker name, or name:style into a style id."""
    try:
        return int(spec)
    except ValueError:
        pass
    name, _, style = spec.partition(":")
    for speaker in fetch_speakers(url):
        if speaker.get("name") != name:
            continue
        styles = speaker.get("styles") or []
        if not styles:
            raise ReaderError(f"speaker {name} has no styles")
        if not style:
            return int(styles[0]["id"])
        for candidate in styles:
            if candidate.get("name") == style:
                return int(candidate["id"])
        known = ", ".join(str(s.get("name", "?")) for s in styles)
        raise ReaderError(f"style not found: {style}. Styles of {name}: {known}")
    raise ReaderError(f"speaker not found: {name}. See --list-speakers")


class VoicevoxEngine(LocalEngine):
    """Talks to a running VOICEVOX engine over HTTP."""

    name = "voicevox"
    ext = "wav"

    def __init__(self, url: str = DEFAULT_URL, speaker: int = 3,
                 speed: float = 1.0, pitch: float = 0.0,
                 intonation: float = 1.0, volume: float = 1.0,
                 timeout: int = 120, jobs: int = 1):
        super().__init__(jobs=jobs)
        self.base = url.rstrip("/")
        self.speaker = speaker
        self.speed = speed
        self.pitch = pitch
        self.intonation = intonation
        self.volume = volume
        self.timeout = timeout

    @property
    def detail(self) -> str:
        return f"speaker {self.speaker}"

    def _post(self, path_and_query: str, body: bytes | None,
              content_type: str | None) -> bytes:
        headers = {"Content-Type": content_type} if content_type else {}
        req = urllib.request.Request(
            f"{self.base}{path_and_query}", data=body, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                data: bytes = res.read()
                return data
        except urllib.error.HTTPError as err:
            raise ReaderError(
                f"VOICEVOX rejected the request ({err.code} {err.reason}). "
                "Check --speaker with --list-speakers."
            ) from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise _unreachable(self.base, err) from err

    def synth_one(self, text: str, path: str) -> None:
        # 1. Build the audio query for this text.
        query = urllib.parse.urlencode({"speaker": self.speaker, "text": text})
        params = json.loads(self._post(f"/audio_query?{query}", None, None))
        # 2. Apply the voice settings.
        params["speedScale"] = self.speed
        params["pitchScale"] = self.pitch
        params["intonationScale"] = self.intonation
        params["volumeScale"] = self.volume
        # 3. Render it to wav.
        wav = self._post(
            f"/synthesis?speaker={self.speaker}",
            json.dumps(params).encode("utf-8"),
            "application/json",
        )
        Path(path).write_bytes(wav)
