"""iroha-reader-cli: documents into audio plus synced subtitles.

The command line lives in `cli`, but every piece is importable:

    from iroha_reader_cli import ConvertOptions, convert
    result = convert(Path("notes.md"), ConvertOptions())
"""

from __future__ import annotations

__version__ = "0.8.0"

from .engines import EngineSettings
from .errors import (
    CommandFailedError,
    EngineNotReadyError,
    MissingCommandError,
    ReaderError,
    UnsupportedInputError,
)
from .pipeline import ConvertOptions, ConvertResult, convert
from .readings import Readings
from .reporting import Reporter
from .timeline import Timeline

__all__ = [
    "CommandFailedError",
    "ConvertOptions",
    "ConvertResult",
    "EngineNotReadyError",
    "EngineSettings",
    "MissingCommandError",
    "ReaderError",
    "Readings",
    "Reporter",
    "Timeline",
    "UnsupportedInputError",
    "__version__",
    "convert",
]
