"""Engine settings and the auto choice."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pytest

from iroha_reader_cli import engines
from iroha_reader_cli.errors import EngineNotReadyError


def settings(**kwargs: object) -> engines.EngineSettings:
    return engines.EngineSettings(**kwargs)  # type: ignore[arg-type]


def test_from_namespace_picks_up_the_engine_flag() -> None:
    args = argparse.Namespace(engine="piper", wpm=200, outdir=Path("x"), speed=1.5)
    resolved = engines.EngineSettings.from_namespace(args)
    assert resolved.requested == "piper"
    assert resolved.wpm == 200
    assert resolved.speed == 1.5


def test_auto_prefers_openjtalk_for_japanese(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engines, "openjtalk_available", lambda _s: True)
    monkeypatch.setattr(engines, "piper_available", lambda _s: True)
    assert engines.choose(settings(), japanese=True) == "openjtalk"


def test_auto_prefers_piper_for_other_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engines, "openjtalk_available", lambda _s: True)
    monkeypatch.setattr(engines, "piper_available", lambda _s: True)
    assert engines.choose(settings(), japanese=False) == "piper"


def test_auto_falls_back_to_espeak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engines, "openjtalk_available", lambda _s: False)
    monkeypatch.setattr(engines, "piper_available", lambda _s: False)
    assert engines.choose(settings(), japanese=True) == "espeak"
    assert engines.choose(settings(), japanese=False) == "espeak"


def test_an_explicit_engine_is_never_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engines, "piper_available", lambda _s: True)
    assert engines.choose(settings(requested="edge"), japanese=True) == "edge"


def test_missing_openjtalk_explains_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engines, "openjtalk_available", lambda _s: False)
    with pytest.raises(EngineNotReadyError, match="apt install open-jtalk"):
        engines.create(settings(requested="openjtalk"), japanese=True)


def test_missing_piper_voice_explains_how_to_get_one(monkeypatch: pytest.MonkeyPatch,
                                                     tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/piper")
    with pytest.raises(EngineNotReadyError, match="download_voices"):
        engines.create(settings(requested="piper", piper_data=tmp_path), japanese=False)


def test_piper_resolves_a_downloaded_voice(monkeypatch: pytest.MonkeyPatch,
                                           tmp_path: Path) -> None:
    (tmp_path / "en_US-lessac-medium.onnx").write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/piper")
    engine = engines.create(settings(requested="piper", piper_data=tmp_path,
                                     piper_length=1.3), japanese=False)
    assert engine.name == "piper"
    assert engine.detail == "en_US-lessac-medium"


def test_edge_picks_a_voice_per_language() -> None:
    japanese = engines.create(settings(requested="edge"), japanese=True)
    english = engines.create(settings(requested="edge"), japanese=False)
    assert japanese.detail.startswith("ja-JP")
    assert english.detail.startswith("en-US")


def test_espeak_language_follows_the_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/espeak-ng")
    assert engines.create(settings(requested="espeak"), japanese=True).detail == "ja"
    assert engines.create(settings(requested="espeak"), japanese=False).detail == "en"


def test_missing_espeak_explains_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    with pytest.raises(EngineNotReadyError, match="apt install espeak-ng"):
        engines.create(settings(requested="espeak"), japanese=True)


def test_word_timing_only_works_with_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/espeak-ng")
    with pytest.raises(EngineNotReadyError, match="needs --engine edge"):
        engines.create(settings(requested="espeak", word_timing=True), japanese=False)


def test_edge_passes_word_timing_on() -> None:
    engine = engines.create(settings(requested="edge", word_timing=True),
                            japanese=False)
    assert engine.word_timing is True
    assert engines.create(settings(requested="edge"), japanese=False).word_timing is False


def test_lrc_style_word_turns_on_word_timing() -> None:
    args = argparse.Namespace(engine="edge", lrc_style="word")
    assert engines.EngineSettings.from_namespace(args).word_timing is True
    args = argparse.Namespace(engine="edge", lrc_style="line")
    assert engines.EngineSettings.from_namespace(args).word_timing is False


def test_an_openjtalk_voice_can_be_named_instead_of_pathed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from iroha_reader_cli.engines import openjtalk

    voice = tmp_path / "mei_normal.htsvoice"
    voice.write_bytes(b"")
    monkeypatch.setattr(openjtalk, "VOICE_DIRS", (tmp_path,))
    assert openjtalk.resolve_voice("mei_normal") == str(voice)
    assert openjtalk.resolve_voice("mei_normal.htsvoice") == str(voice)
    assert openjtalk.resolve_voice("nothing_like_it") is None


def test_the_default_voice_falls_back_to_mei(monkeypatch: pytest.MonkeyPatch,
                                             tmp_path: Path) -> None:
    from iroha_reader_cli.engines import openjtalk

    (tmp_path / "nitech_jp_atr503_m001.htsvoice").write_bytes(b"")
    mei = tmp_path / "mei_happy.htsvoice"
    mei.write_bytes(b"")
    monkeypatch.setattr(openjtalk, "VOICE_DIRS", (tmp_path,))
    # The apt default is not installed at its usual path here, so the
    # nicest installed voice wins.
    assert openjtalk.resolve_voice(str(openjtalk.DEFAULT_VOICE)) == str(mei)


def test_an_unknown_openjtalk_voice_lists_what_is_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from iroha_reader_cli.engines import openjtalk

    (tmp_path / "mei_normal.htsvoice").write_bytes(b"")
    (tmp_path / "dict").mkdir()
    monkeypatch.setattr(openjtalk, "VOICE_DIRS", (tmp_path,))
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/open_jtalk")
    with pytest.raises(EngineNotReadyError, match="Installed: mei_normal"):
        engines.create(
            settings(requested="openjtalk", ojt_voice="ghost",
                     ojt_dict=str(tmp_path / "dict")),
            japanese=True,
        )


def test_speed_reaches_every_engine(monkeypatch: pytest.MonkeyPatch,
                                    tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/anything")
    (tmp_path / "voice.onnx").write_bytes(b"")

    fast = engines.EngineSettings(speed=2.0, piper_data=tmp_path,
                                  piper_model="voice")
    assert fast.espeak_wpm() == engines.DEFAULT_WPM * 2
    # Piper measures length, so twice the speed is half the length.
    assert fast.piper_length_scale() == 0.5
    assert fast.voicevox_speed() == 2.0
    assert fast.edge_rate() == "+100%"

    slow = engines.EngineSettings(speed=0.5)
    assert slow.espeak_wpm() == round(engines.DEFAULT_WPM * 0.5)
    assert slow.piper_length_scale() == 2.0
    assert slow.edge_rate() == "-50%"


def test_the_engine_specific_setting_wins() -> None:
    settings = engines.EngineSettings(speed=2.0, wpm=100, piper_length=3.0,
                                      vv_speed=0.8, rate="+5%")
    assert settings.espeak_wpm() == 100
    assert settings.piper_length_scale() == 3.0
    assert settings.voicevox_speed() == 0.8
    assert settings.edge_rate() == "+5%"


def test_the_default_speed_changes_nothing() -> None:
    plain = engines.EngineSettings()
    assert plain.espeak_wpm() == engines.DEFAULT_WPM
    assert plain.piper_length_scale() == 1.0
    assert plain.voicevox_speed() == 1.0
    assert plain.edge_rate() == "+0%"


@pytest.mark.parametrize("speed", [0.0, -1.0])
def test_a_speed_of_zero_or_less_is_rejected(speed: float) -> None:
    from iroha_reader_cli.errors import ReaderError

    with pytest.raises(ReaderError, match="--speed"):
        engines.EngineSettings(speed=speed)


def test_speed_reaches_the_built_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/usr/bin/espeak-ng")
    engine = engines.create(settings(requested="espeak", speed=1.5), japanese=False)
    assert engine.wpm == round(engines.DEFAULT_WPM * 1.5)  # type: ignore[attr-defined]

    edge_engine = engines.create(settings(requested="edge", speed=1.5), japanese=False)
    assert edge_engine.rate == "+50%"  # type: ignore[attr-defined]
