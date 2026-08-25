"""Flag parsing, config merging, and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest

from iroha_reader_cli import cli
from iroha_reader_cli.errors import ReaderError


@pytest.fixture(autouse=True)
def no_user_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's own config file out of the tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def test_defaults() -> None:
    args = cli.parse_args(["notes.md"])
    assert args.inputs == [Path("notes.md")]
    assert args.engine == "auto"
    assert args.audio_format == "mp3"
    assert args.subs is None
    assert cli.build_options(args).subtitle_formats == ("lrc",)


def test_subs_accepts_commas_and_repeats() -> None:
    assert cli.parse_args(["a.md", "--subs", "lrc,srt"]).subs == ["lrc", "srt"]
    args = cli.parse_args(["a.md", "--subs", "srt", "--subs", "vtt"])
    assert args.subs == ["srt", "vtt"]


def test_subs_does_not_repeat_a_format() -> None:
    assert cli.parse_args(["a.md", "--subs", "srt,srt"]).subs == ["srt"]


def test_the_config_file_supplies_defaults(tmp_path: Path) -> None:
    config = tmp_path / "c.toml"
    config.write_text('engine = "espeak"\ngap-ms = 150\nsubs = ["lrc", "srt"]\n',
                      encoding="utf-8")
    args = cli.parse_args(["a.md", "--config", str(config)])
    assert args.engine == "espeak"
    assert args.gap_ms == 150
    assert cli.build_options(args).subtitle_formats == ("lrc", "srt")


def test_the_command_line_beats_the_config_file(tmp_path: Path) -> None:
    config = tmp_path / "c.toml"
    config.write_text('engine = "espeak"\nsubs = ["lrc", "srt"]\n', encoding="utf-8")
    args = cli.parse_args(["a.md", "--config", str(config), "--engine", "edge",
                           "--subs", "vtt"])
    assert args.engine == "edge"
    # The flag replaces the config list instead of adding to it.
    assert cli.build_options(args).subtitle_formats == ("vtt",)


def test_an_unknown_config_key_warns(tmp_path: Path,
                                     capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "c.toml"
    config.write_text('nonsense = 1\n', encoding="utf-8")
    cli.parse_args(["a.md", "--config", str(config)])
    assert "unknown config key: nonsense" in capsys.readouterr().err


def test_the_config_alias_for_dict(tmp_path: Path) -> None:
    config = tmp_path / "c.toml"
    config.write_text('dict = "readings.tsv"\nformat = "wav"\n', encoding="utf-8")
    args = cli.parse_args(["a.md", "--config", str(config)])
    # argparse applies the flag's type to a string default, so this is a Path.
    assert args.dict_file == Path("readings.tsv")
    assert args.audio_format == "wav"


def test_config_paths_become_path_objects(tmp_path: Path) -> None:
    config = tmp_path / "c.toml"
    config.write_text(f'outdir = "{tmp_path}/out"\n', encoding="utf-8")
    options = cli.build_options(cli.parse_args(["a.md", "--config", str(config)]))
    assert options.outdir == tmp_path / "out"


def test_build_options_copies_the_flags() -> None:
    args = cli.parse_args(["a.pdf", "--pages", "2-4", "--gap-ms", "0", "--loudnorm",
                           "--max-chars", "30", "--keep-code", "--bitrate", "128k"])
    options = cli.build_options(args)
    assert options.pages == (2, 4)
    assert options.gap_ms == 0
    assert options.loudnorm is True
    assert options.max_chars == 30
    assert options.keep_code is True
    assert options.bitrate == "128k"


def test_engine_settings_come_from_the_same_flags() -> None:
    from iroha_reader_cli.engines import EngineSettings

    args = cli.parse_args(["a.md", "--engine", "voicevox", "--speaker", "Zundamon",
                           "--vv-speed", "1.2", "--jobs", "8"])
    settings = EngineSettings.from_namespace(args)
    assert settings.requested == "voicevox"
    assert settings.speaker == "Zundamon"
    assert settings.vv_speed == 1.2
    assert settings.jobs == 8


def test_version_prints_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["--version"])
    assert exit_info.value.code == 0
    assert "iroha-reader-cli" in capsys.readouterr().out


def test_no_inputs_is_an_error() -> None:
    with pytest.raises(ReaderError, match="no input files"):
        cli.run([])


def test_name_with_many_inputs_is_an_error() -> None:
    with pytest.raises(ReaderError, match="one input file only"):
        cli.run(["a.md", "b.md", "--name", "both"])


def test_main_turns_an_error_into_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["missing.md", "--dry-run", "--quiet"]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error: file not found")
    assert "Traceback" not in err


def test_main_reports_an_interrupt(monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    def boom(_argv: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run", boom)
    assert cli.main(["a.md"]) == cli.EXIT_INTERRUPTED
    assert "interrupted" in capsys.readouterr().err


def test_dry_run_prints_the_lines(tmp_path: Path,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Head\n\nBody text.\n", encoding="utf-8")
    assert cli.main([str(source), "--dry-run", "--quiet"]) == cli.EXIT_OK
    out = capsys.readouterr()
    assert out.out == "Head\nBody text.\n"
    assert out.err == ""


def test_subs_from_a_config_string(tmp_path: Path) -> None:
    config = tmp_path / "c.toml"
    config.write_text('subs = "lrc, vtt"\n', encoding="utf-8")
    options = cli.build_options(cli.parse_args(["a.md", "--config", str(config)]))
    assert options.subtitle_formats == ("lrc", "vtt")
