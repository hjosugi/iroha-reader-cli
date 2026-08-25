"""The TOML config file."""

from __future__ import annotations

from pathlib import Path

import pytest

from iroha_reader_cli import config
from iroha_reader_cli.errors import ReaderError


def test_default_path_follows_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert config.default_path() == Path("/tmp/xdg/iroha-reader-cli/config.toml")


def test_default_path_falls_back_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config.default_path().parts[-3:] == (".config", "iroha-reader-cli", "config.toml")


def test_a_missing_default_file_is_fine(monkeypatch: pytest.MonkeyPatch,
                                        tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.load() == {}


def test_a_missing_explicit_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="config file not found"):
        config.load(tmp_path / "nope.toml")


def test_broken_toml_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("engine = \n", encoding="utf-8")
    with pytest.raises(ReaderError, match="bad config file"):
        config.load(path)


def test_load_reads_values(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text('engine = "espeak"\ngap-ms = 150\n', encoding="utf-8")
    assert config.load(path) == {"engine": "espeak", "gap-ms": 150}


def test_to_defaults_maps_dashes_and_aliases() -> None:
    defaults, unknown = config.to_defaults(
        {"gap-ms": 150, "dict": "d.tsv", "nope": 1},
        valid={"gap_ms", "dict_file"},
        aliases={"dict": "dict_file"},
    )
    assert defaults == {"gap_ms": 150, "dict_file": "d.tsv"}
    assert unknown == ["nope"]


def test_a_profile_overrides_the_top_level_keys() -> None:
    merged = config.select_profile(
        {"engine": "espeak", "gap-ms": 200,
         "profile": {"study": {"engine": "voicevox", "vv-speed": 1.3}}},
        "study",
    )
    assert merged == {"engine": "voicevox", "gap-ms": 200, "vv-speed": 1.3}


def test_without_a_profile_only_the_top_level_keys_are_used() -> None:
    merged = config.select_profile(
        {"engine": "espeak", "profile": {"study": {"engine": "voicevox"}}}, None
    )
    assert merged == {"engine": "espeak"}


def test_an_unknown_profile_lists_the_ones_that_exist() -> None:
    with pytest.raises(ReaderError, match="relax, study"):
        config.select_profile({"profile": {"study": {}, "relax": {}}}, "focus")


def test_a_profile_without_a_config_file_says_so() -> None:
    with pytest.raises(ReaderError, match="none"):
        config.select_profile({}, "study")


def test_a_profile_must_be_a_table() -> None:
    with pytest.raises(ReaderError, match="table of settings"):
        config.select_profile({"profile": {"study": "espeak"}}, "study")
