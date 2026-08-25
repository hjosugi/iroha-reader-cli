"""Running external commands."""

from __future__ import annotations

import subprocess
import sys

import pytest

from iroha_reader_cli.errors import CommandFailedError, MissingCommandError
from iroha_reader_cli.proc import child_environment, run


def test_a_missing_command_says_which_one() -> None:
    with pytest.raises(MissingCommandError, match="no-such-command-anywhere"):
        run(["no-such-command-anywhere"])


def test_a_failing_command_carries_its_stderr() -> None:
    with pytest.raises(CommandFailedError, match="deliberate failure"):
        run([sys.executable, "-c", "import sys; sys.exit(sys.stderr.write("
                                   "'deliberate failure') and 1 or 1)"])


def test_output_comes_back() -> None:
    result = run([sys.executable, "-c", "print('hello')"])
    assert result.stdout.strip() == b"hello"


def test_stdin_reaches_the_command() -> None:
    result = run([sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                 stdin=b"through stdin")
    assert result.stdout == b"through stdin"


def test_a_normal_run_inherits_the_environment() -> None:
    assert child_environment() is None


def test_a_frozen_build_hands_back_the_original_library_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/mine")

    env = child_environment()
    assert env is not None
    # The bundled path would make the system ffmpeg load our libstdc++.
    assert env["LD_LIBRARY_PATH"] == "/usr/lib/mine"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_a_frozen_build_drops_the_path_when_there_was_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    env = child_environment()
    assert env is not None
    assert "LD_LIBRARY_PATH" not in env


def test_the_frozen_environment_keeps_everything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/home/someone")

    env = child_environment()
    assert env is not None
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/someone"


def test_subprocess_actually_gets_that_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI12345")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/mine")

    result = run([sys.executable, "-c",
                  "import os; print(os.environ.get('LD_LIBRARY_PATH', 'unset'))"])
    assert result.stdout.strip() == b"/usr/lib/mine"


def test_the_exit_code_is_reported() -> None:
    with pytest.raises(CommandFailedError) as failure:
        run([sys.executable, "-c", "raise SystemExit(3)"])
    assert isinstance(failure.value.__cause__, subprocess.CalledProcessError)
    assert failure.value.returncode == 3
