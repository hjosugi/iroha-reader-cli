"""--list-speakers, for every engine."""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from iroha_reader_cli import speakers
from iroha_reader_cli.engines import EngineSettings, edge, openjtalk, voicevox
from iroha_reader_cli.errors import EngineNotReadyError, MissingCommandError

SPEAKERS = [{"name": "Zundamon", "styles": [{"id": 3, "name": "Normal"}]}]


def listed(settings: EngineSettings) -> str:
    out = io.StringIO()
    speakers.list_speakers(settings, out)
    return out.getvalue()


def test_voicevox_styles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voicevox, "fetch_speakers", lambda _u, **_kw: SPEAKERS)
    text = listed(EngineSettings(requested="voicevox"))
    assert "3  Zundamon (Normal)" in text
    assert "--speaker" in text


def test_openjtalk_voices(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "mei_normal.htsvoice").write_bytes(b"")
    monkeypatch.setattr(openjtalk, "VOICE_DIRS", (tmp_path,))
    text = listed(EngineSettings(requested="openjtalk"))
    assert "mei_normal" in text
    assert str(tmp_path / "mei_normal.htsvoice") in text


def test_openjtalk_with_nothing_installed(monkeypatch: pytest.MonkeyPatch,
                                          tmp_path: Path) -> None:
    monkeypatch.setattr(openjtalk, "VOICE_DIRS", (tmp_path / "empty",))
    text = listed(EngineSettings(requested="openjtalk"))
    assert "none found" in text
    assert str(tmp_path / "empty") in text


def test_piper_voices(tmp_path: Path) -> None:
    (tmp_path / "en_US-amy-medium.onnx").write_bytes(b"")
    text = listed(EngineSettings(requested="piper", piper_data=tmp_path))
    assert "en_US-amy-medium" in text
    assert "download_voices" in text


def test_piper_with_nothing_downloaded(tmp_path: Path) -> None:
    text = listed(EngineSettings(requested="piper", piper_data=tmp_path / "none"))
    assert "none found" in text


def test_espeak_voices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/espeak-ng")

    def fake_run(argv: list[str], stdin: bytes | None = None) -> Any:
        assert argv[1] == "--voices=ja"
        return subprocess.CompletedProcess(argv, 0, b"Pty Language\n 5  ja\n", b"")

    monkeypatch.setattr(speakers, "run", fake_run)
    text = listed(EngineSettings(requested="espeak", lang="ja"))
    assert "5  ja" in text
    assert "--lang" in text


def test_espeak_without_espeak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    with pytest.raises(MissingCommandError, match="espeak-ng is missing"):
        listed(EngineSettings(requested="espeak"))


def test_edge_voices_can_be_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    voices = [
        {"ShortName": "ja-JP-NanamiNeural", "Gender": "Female", "Locale": "ja-JP"},
        {"ShortName": "en-US-JennyNeural", "Gender": "Female", "Locale": "en-US"},
    ]

    async def fake_list() -> list[dict[str, str]]:
        return voices

    monkeypatch.setattr(edge, "list_voices", fake_list)
    text = listed(EngineSettings(requested="edge", lang="ja"))
    assert "ja-JP-NanamiNeural" in text
    assert "en-US-JennyNeural" not in text

    everything = listed(EngineSettings(requested="edge"))
    assert "en-US-JennyNeural" in everything


def test_auto_prefers_a_running_voicevox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voicevox, "fetch_speakers", lambda _u, **_kw: SPEAKERS)
    assert "Zundamon" in listed(EngineSettings())


def test_auto_falls_back_when_voicevox_is_not_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuse(_url: str, **_kw: object) -> list[dict[str, Any]]:
        raise EngineNotReadyError("not running")

    monkeypatch.setattr(voicevox, "fetch_speakers", refuse)
    monkeypatch.setattr(openjtalk, "VOICE_DIRS", (tmp_path,))
    (tmp_path / "mei_normal.htsvoice").write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/open_jtalk")
    monkeypatch.setattr(Path, "is_dir", lambda _self: True)

    text = listed(EngineSettings())
    assert "mei_normal" in text
