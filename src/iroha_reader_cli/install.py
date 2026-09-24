"""How to install the external commands, on the system in front of us.

The tool runs on Linux, macOS, and Windows, but every one of them gets
ffmpeg and the engines from a different place. The error for a missing
command names the way that works here, not the Debian one everywhere.
"""

from __future__ import annotations

import sys

#: Where each package comes from, per `sys.platform` family.
_PACKAGES: dict[str, dict[str, str]] = {
    "ffmpeg": {
        "linux": "sudo apt install ffmpeg",
        "darwin": "brew install ffmpeg",
        "win32": "winget install Gyan.FFmpeg",
    },
    "espeak-ng": {
        "linux": "sudo apt install espeak-ng",
        "darwin": "brew install espeak-ng",
        "win32": ("run espeak-ng.msi from "
                  "https://github.com/espeak-ng/espeak-ng/releases"),
    },
    "poppler": {
        "linux": "sudo apt install poppler-utils",
        "darwin": "brew install poppler",
        "win32": "winget install oschwartz10612.Poppler",
    },
}

_NAMES = {"linux": "Debian/Ubuntu", "darwin": "macOS, Homebrew", "win32": "Windows"}


def family(platform: str | None = None) -> str:
    """linux, darwin, or win32 for this machine (other unixes count as linux)."""
    platform = sys.platform if platform is None else platform
    if platform.startswith("win") or platform == "cygwin":
        return "win32"
    if platform == "darwin":
        return "darwin"
    return "linux"


def command(package: str, platform: str | None = None) -> str | None:
    """The install command for `package` here, or None when there is no packaged one."""
    return _PACKAGES[package].get(family(platform))


def hint(package: str, platform: str | None = None) -> str:
    """`(Debian/Ubuntu: sudo apt install x)`, or its equivalent here."""
    here = family(platform)
    found = _PACKAGES[package].get(here)
    if found is None:
        # No package on this system: show the Linux one, which says what to look for.
        return f"({_NAMES['linux']}: {_PACKAGES[package]['linux']})"
    return f"({_NAMES[here]}: {found})"
