"""Shell completion scripts."""

from __future__ import annotations

import pytest

from iroha_reader_cli import completion
from iroha_reader_cli.cli import build_parser


@pytest.fixture
def parser() -> object:
    return build_parser()


def long_flags() -> list[str]:
    return [flag for action in build_parser()._actions
            for flag in action.option_strings if flag.startswith("--")]


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_every_flag_is_in_every_script(shell: str) -> None:
    # The scripts are generated from the parser precisely so that this
    # cannot drift.
    script = completion.script(shell, build_parser(), "irh")
    missing = [flag for flag in long_flags()
               if flag not in script and flag.lstrip("-") not in script]
    assert missing == []


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_the_script_names_the_command(shell: str) -> None:
    assert "irh" in completion.script(shell, build_parser(), "irh")


def test_fish_offers_the_engine_names() -> None:
    script = completion.script("fish", build_parser(), "irh")
    assert ("complete -c irh -l engine -x -a 'auto espeak openjtalk piper "
            "voicevox edge'") in script
    # A switch takes no argument, so it must not be marked -r.
    assert "-l loudnorm -d" in script


def test_bash_defines_a_function_and_a_completion() -> None:
    script = completion.script("bash", build_parser(), "iroha-reader-cli")
    assert "_iroha_reader_cli_complete()" in script
    assert "complete -o filenames -F _iroha_reader_cli_complete iroha-reader-cli" in script
    assert 'COMPREPLY=($(compgen -W "auto espeak openjtalk piper voicevox edge"' in script


def test_zsh_starts_with_the_compdef_line() -> None:
    script = completion.script("zsh", build_parser(), "irh")
    assert script.startswith("#compdef irh\n")
    assert "_arguments -s" in script
    assert "*.(md|markdown|epub|pdf|txt|text)" in script


def test_an_unknown_shell_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown shell: ksh"):
        completion.script("ksh", build_parser(), "irh")


@pytest.mark.parametrize(
    ("help_text", "expected"),
    [
        ("output directory (default: next to the input)", "output directory"),
        ("speech rate, like +10%% (default: +0%%)", "speech rate"),
        ("open a local web page instead: drop a document on it",
         "open a local web page instead"),
        ("", ""),
    ],
)
def test_descriptions_are_cut_down_to_one_short_phrase(help_text: str,
                                                       expected: str) -> None:
    assert completion._first_sentence(help_text) == expected


def test_a_long_description_is_cut_at_a_word() -> None:
    long = "a description that runs on well past the limit of sixty characters"
    short = completion._first_sentence(long)
    assert len(short) <= 60
    assert not short.endswith(" ")
    assert long.startswith(short)


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_the_script_is_a_single_trailing_newline(shell: str) -> None:
    script = completion.script(shell, build_parser(), "irh")
    assert script.endswith("\n")
    assert not script.endswith("\n\n")
