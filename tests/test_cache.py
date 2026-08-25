"""The segment cache."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from iroha_reader_cli.cache import CachedEngine, SegmentCache, default_dir, key_for
from iroha_reader_cli.engines.base import Engine, LocalEngine
from iroha_reader_cli.engines.espeak import EspeakEngine
from iroha_reader_cli.reporting import Reporter


class CountingEngine(LocalEngine):
    """Writes the text into the file and counts what it was asked for."""

    name = "counting"
    ext = "wav"

    def __init__(self) -> None:
        super().__init__(jobs=1)
        self.calls: list[str] = []

    def synth_one(self, text: str, path: str) -> None:
        self.calls.append(text)
        Path(path).write_text(text, encoding="utf-8")


def outdir(root: Path, name: str) -> str:
    """An existing directory for the segments, the way the pipeline provides one."""
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def test_default_dir_follows_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg-cache")
    assert default_dir() == Path("/tmp/xdg-cache/iroha-reader-cli/segments")


def test_the_key_covers_the_text_and_the_settings() -> None:
    base = {"engine": "espeak", "wpm": "175"}
    assert key_for(base, "hello") == key_for(dict(base), "hello")
    assert key_for(base, "hello") != key_for(base, "goodbye")
    assert key_for(base, "hello") != key_for({**base, "wpm": "220"}, "hello")


def test_speed_changes_the_signature_but_worker_count_does_not() -> None:
    slow = EspeakEngine(lang="en", wpm=120, jobs=1).signature()
    fast = EspeakEngine(lang="en", wpm=240, jobs=1).signature()
    parallel = EspeakEngine(lang="en", wpm=120, jobs=8).signature()
    assert slow != fast
    assert slow == parallel


def test_a_changed_voice_file_misses_even_at_the_same_path(tmp_path: Path) -> None:
    from iroha_reader_cli.engines.piper import PiperEngine

    voice = tmp_path / "voice.onnx"
    voice.write_bytes(b"first")
    before = PiperEngine(str(voice)).signature()
    voice.write_bytes(b"a longer second version")
    assert PiperEngine(str(voice)).signature() != before


def test_store_and_fetch(tmp_path: Path) -> None:
    cache = SegmentCache(tmp_path)
    source = tmp_path / "seg.wav"
    source.write_bytes(b"audio")

    assert cache.get("abc123", "wav") is None
    cache.put("abc123", "wav", source)
    hit = cache.get("abc123", "wav")
    assert hit is not None
    assert hit.read_bytes() == b"audio"
    # The first two characters fan the files out into directories.
    assert hit.parent.name == "ab"


def test_clear_reports_what_it_freed(tmp_path: Path) -> None:
    cache = SegmentCache(tmp_path / "store")
    source = tmp_path / "seg.wav"
    source.write_bytes(b"12345")
    cache.put("aaaa", "wav", source)
    cache.put("bbbb", "wav", source)

    assert cache.clear() == (2, 10)
    assert cache.clear() == (0, 0)


def test_a_second_run_synthesizes_nothing(tmp_path: Path) -> None:
    cache = SegmentCache(tmp_path / "store")
    lines = ["one", "two", "three"]

    first = CountingEngine()
    CachedEngine(first, cache).synth_all(lines, outdir(tmp_path, "a"), Reporter(quiet=True))
    assert first.calls == lines

    second = CountingEngine()
    wrapped = CachedEngine(second, cache)
    paths = wrapped.synth_all(lines, outdir(tmp_path, "b"), Reporter(quiet=True))
    assert second.calls == []
    assert wrapped.reused == 3
    assert [Path(p).read_text(encoding="utf-8") for p in paths] == lines


def test_only_the_changed_line_is_synthesized_again(tmp_path: Path) -> None:
    cache = SegmentCache(tmp_path / "store")
    first = CountingEngine()
    CachedEngine(first, cache).synth_all(["one", "two"], outdir(tmp_path, "a"),
                                         Reporter(quiet=True))

    second = CountingEngine()
    paths = CachedEngine(second, cache).synth_all(
        ["one", "edited"], outdir(tmp_path, "b"), Reporter(quiet=True)
    )
    assert second.calls == ["edited"]
    assert [Path(p).read_text(encoding="utf-8") for p in paths] == ["one", "edited"]


def test_different_settings_do_not_share_segments(tmp_path: Path) -> None:
    cache = SegmentCache(tmp_path / "store")

    class Slower(CountingEngine):
        def __init__(self) -> None:
            super().__init__()
            self.wpm = 120

    fast = CountingEngine()
    CachedEngine(fast, cache).synth_all(["one"], outdir(tmp_path, "a"),
                                        Reporter(quiet=True))
    slow = Slower()
    CachedEngine(slow, cache).synth_all(["one"], outdir(tmp_path, "b"),
                                        Reporter(quiet=True))
    assert slow.calls == ["one"]


def test_the_cache_hit_is_reported(tmp_path: Path,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    cache = SegmentCache(tmp_path / "store")
    CachedEngine(CountingEngine(), cache).synth_all(
        ["one"], outdir(tmp_path, "a"), Reporter(quiet=True)
    )
    CachedEngine(CountingEngine(), cache).synth_all(
        ["one"], outdir(tmp_path, "b"), Reporter()
    )
    assert "cache: 1/1 lines reused" in capsys.readouterr().err


def test_an_unwritable_cache_is_not_fatal(tmp_path: Path) -> None:
    unwritable = tmp_path / "no-write"
    unwritable.mkdir(mode=0o500)
    cache = SegmentCache(unwritable / "store")
    engine = CountingEngine()
    paths = CachedEngine(engine, cache).synth_all(["one"], outdir(tmp_path, "a"),
                                                  Reporter(quiet=True))
    assert engine.calls == ["one"]
    assert Path(paths[0]).read_text(encoding="utf-8") == "one"


def test_the_wrapper_keeps_the_engine_identity() -> None:
    class Fake(Engine):
        name = "fake"
        ext = "mp3"

        @property
        def detail(self) -> str:
            return "a voice"

        def synth_all(self, lines: Sequence[str], outdir: str,
                      reporter: Reporter) -> list[str]:
            return []

    wrapped = CachedEngine(Fake(), SegmentCache(Path("/nowhere")))
    assert (wrapped.name, wrapped.ext, wrapped.detail) == ("fake", "mp3", "a voice")


def test_bookkeeping_attributes_stay_out_of_the_signature() -> None:
    engine = CountingEngine()
    before = engine.signature()
    engine.calls.append("something happened")
    assert engine.signature() == before


def test_a_repeated_line_is_spoken_once_on_the_first_run(tmp_path: Path) -> None:
    cache = SegmentCache(tmp_path / "store")
    engine = CountingEngine()
    wrapped = CachedEngine(engine, cache)
    lines = ["chorus", "verse", "chorus", "chorus"]

    paths = wrapped.synth_all(lines, outdir(tmp_path, "a"), Reporter(quiet=True))

    assert engine.calls == ["chorus", "verse"]
    assert wrapped.repeats == 2
    assert [Path(p).read_text(encoding="utf-8") for p in paths] == lines
