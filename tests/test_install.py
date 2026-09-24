"""Install hints and finding espeak-ng on each operating system."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from iroha_reader_cli import install
from iroha_reader_cli.engines import espeak


@pytest.mark.parametrize(("platform", "family"), [
    ("linux", "linux"),
    ("freebsd14", "linux"),
    ("darwin", "darwin"),
    ("win32", "win32"),
    ("cygwin", "win32"),
])
def test_the_platform_family(platform: str, family: str) -> None:
    assert install.family(platform) == family


def test_each_platform_gets_its_own_package_manager() -> None:
    assert install.hint("ffmpeg", "linux") == "(Debian/Ubuntu: sudo apt install ffmpeg)"
    assert install.hint("ffmpeg", "darwin") == "(macOS, Homebrew: brew install ffmpeg)"
    assert install.hint("ffmpeg", "win32") == "(Windows: winget install Gyan.FFmpeg)"
    assert install.command("espeak-ng", "darwin") == "brew install espeak-ng"
    assert "espeak-ng.msi" in install.hint("espeak-ng", "win32")
    assert install.command("poppler", "linux") == "sudo apt install poppler-utils"


def test_the_hint_follows_this_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "brew install espeak-ng" in espeak.missing_message()


def test_espeak_on_path_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _c: "/opt/bin/espeak-ng")
    assert espeak.find_command() == "/opt/bin/espeak-ng"


def test_espeak_from_the_windows_installer(monkeypatch: pytest.MonkeyPatch,
                                           tmp_path: Path) -> None:
    installed = tmp_path / "eSpeak NG" / "espeak-ng.exe"
    installed.parent.mkdir()
    installed.write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("ProgramW6432", str(tmp_path))
    assert espeak.find_command() == str(installed)


def test_no_installer_lookup_off_windows(monkeypatch: pytest.MonkeyPatch,
                                         tmp_path: Path) -> None:
    (tmp_path / "eSpeak NG").mkdir()
    (tmp_path / "eSpeak NG" / "espeak-ng.exe").write_bytes(b"")
    monkeypatch.setattr(shutil, "which", lambda _c: None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert espeak.find_command() is None
