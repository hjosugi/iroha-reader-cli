"""The VOICEVOX engine, against a fake engine server."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from iroha_reader_cli.engines import voicevox
from iroha_reader_cli.engines.voicevox import VoicevoxEngine, fetch_speakers, resolve_speaker
from iroha_reader_cli.errors import EngineNotReadyError, ReaderError
from iroha_reader_cli.reporting import Reporter

SPEAKERS = [
    {"name": "Zundamon", "styles": [{"id": 3, "name": "Normal"},
                                    {"id": 1, "name": "Amaama"}]},
    {"name": "Metan", "styles": [{"id": 2, "name": "Normal"}]},
]


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every request and answer it the way the engine would."""
    seen: list[dict[str, Any]] = []

    def fake_urlopen(request: Any, timeout: float = 0) -> FakeResponse:
        url = request if isinstance(request, str) else request.full_url
        body = None if isinstance(request, str) else request.data
        seen.append({"url": url, "body": body})
        if "/speakers" in url:
            return FakeResponse(json.dumps(SPEAKERS).encode())
        if "/audio_query" in url:
            return FakeResponse(json.dumps({"speedScale": 1.0, "accent_phrases": []}).encode())
        if "/synthesis" in url:
            return FakeResponse(b"RIFFfake-wav-bytes")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_speakers_come_back_as_a_list(calls: list[dict[str, Any]]) -> None:
    assert fetch_speakers("http://127.0.0.1:50021/")[0]["name"] == "Zundamon"
    assert calls[0]["url"] == "http://127.0.0.1:50021/speakers"


def test_a_plain_id_needs_no_lookup(calls: list[dict[str, Any]]) -> None:
    assert resolve_speaker("8", voicevox.DEFAULT_URL) == 8
    assert calls == []


def test_a_name_resolves_to_its_first_style(calls: list[dict[str, Any]]) -> None:
    assert resolve_speaker("Zundamon", voicevox.DEFAULT_URL) == 3


def test_a_name_and_style_resolve_together(calls: list[dict[str, Any]]) -> None:
    assert resolve_speaker("Zundamon:Amaama", voicevox.DEFAULT_URL) == 1


def test_an_unknown_style_lists_the_ones_that_exist(calls: list[dict[str, Any]]) -> None:
    with pytest.raises(ReaderError, match="Normal, Amaama"):
        resolve_speaker("Zundamon:Shouting", voicevox.DEFAULT_URL)


def test_an_unknown_speaker_says_so(calls: list[dict[str, Any]]) -> None:
    with pytest.raises(ReaderError, match="speaker not found: Nobody"):
        resolve_speaker("Nobody", voicevox.DEFAULT_URL)


def test_a_stopped_engine_says_how_to_fix_it(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(EngineNotReadyError, match="Start the engine"):
        fetch_speakers(voicevox.DEFAULT_URL)


def test_synthesis_sends_the_voice_settings(calls: list[dict[str, Any]],
                                            tmp_path: Path) -> None:
    engine = VoicevoxEngine(speaker=8, speed=1.3, pitch=0.05, intonation=1.2,
                            volume=0.9)
    segments = engine.synth_all(["こんにちは"], str(tmp_path), Reporter(quiet=True))

    assert Path(segments.paths[0]).read_bytes() == b"RIFFfake-wav-bytes"
    query = calls[0]["url"]
    assert "/audio_query?" in query and "speaker=8" in query
    sent = json.loads(calls[1]["body"])
    assert sent["speedScale"] == 1.3
    assert sent["pitchScale"] == 0.05
    assert sent["intonationScale"] == 1.2
    assert sent["volumeScale"] == 0.9


def test_a_rejected_request_names_the_speaker_flag(monkeypatch: pytest.MonkeyPatch,
                                                   tmp_path: Path) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise urllib.error.HTTPError("http://x", 422, "Unprocessable", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(ReaderError, match="--speaker"):
        VoicevoxEngine().synth_all(["x"], str(tmp_path), Reporter(quiet=True))


def test_the_engine_reports_its_speaker() -> None:
    assert VoicevoxEngine(speaker=8).detail == "speaker 8"


def test_a_nonsense_speakers_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *_a, **_kw: FakeResponse(b'{"not": "a list"}'))
    with pytest.raises(EngineNotReadyError, match="unexpected"):
        fetch_speakers(voicevox.DEFAULT_URL)
