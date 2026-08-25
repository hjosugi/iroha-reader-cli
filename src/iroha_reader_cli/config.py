"""Optional TOML config file.

Keys are the long option names without the leading dashes, so
`gap-ms = 150` in the file is the same as `--gap-ms 150` on the
command line. The command line always wins.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from .errors import ReaderError

APP_NAME = "iroha-reader-cli"


def default_path() -> Path:
    """Return ~/.config/iroha-reader-cli/config.toml (XDG aware)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path("~/.config").expanduser()
    return root / APP_NAME / "config.toml"


def load(explicit: Path | None = None) -> dict[str, Any]:
    """Read the config file. An explicit path must exist; the default may not."""
    path = explicit if explicit is not None else default_path()
    if not path.is_file():
        if explicit is not None:
            raise ReaderError(f"config file not found: {path}")
        return {}
    try:
        with path.open("rb") as f:
            data: dict[str, Any] = tomllib.load(f)
        return data
    except tomllib.TOMLDecodeError as err:
        raise ReaderError(f"bad config file {path}: {err}") from err
    except OSError as err:
        raise ReaderError(f"cannot read config file {path}: {err}") from err


PROFILE_TABLE = "profile"


def select_profile(config: dict[str, Any], name: str | None) -> dict[str, Any]:
    """Fold one [profile.NAME] table into the top level keys.

    Profile keys win over the top level ones; the command line still
    wins over both.
    """
    profiles = config.get(PROFILE_TABLE) or {}
    base = {key: value for key, value in config.items() if key != PROFILE_TABLE}
    if name is None:
        return base
    if not isinstance(profiles, dict) or name not in profiles:
        known = ", ".join(sorted(profiles)) if isinstance(profiles, dict) else ""
        raise ReaderError(
            f"profile not found: {name}. "
            f"Profiles in the config file: {known or 'none'}"
        )
    chosen = profiles[name]
    if not isinstance(chosen, dict):
        raise ReaderError(f"[{PROFILE_TABLE}.{name}] must be a table of settings")
    base.update(chosen)
    return base


def to_defaults(config: dict[str, Any], valid: set[str],
                aliases: dict[str, str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Map config keys onto argparse destinations.

    Returns the defaults plus the names of any keys that were skipped.
    """
    aliases = aliases or {}
    defaults: dict[str, Any] = {}
    unknown: list[str] = []
    for key, value in config.items():
        dest = aliases.get(key, key.replace("-", "_"))
        if dest not in valid:
            unknown.append(key)
            continue
        defaults[dest] = value
    return defaults, unknown
