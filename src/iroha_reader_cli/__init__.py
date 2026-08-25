"""iroha-reader-cli: documents into audio plus synced subtitles.

The command line lives in `cli`, but every piece is importable:

    from iroha_reader_cli import ConvertOptions, convert
    result = convert(Path("notes.md"), ConvertOptions())
"""

from __future__ import annotations

__version__ = "0.11.0"

from .document import Block, Chapter, Line
from .engines import EngineSettings
from .errors import (
    CommandFailedError,
    EngineNotReadyError,
    MissingCommandError,
    ReaderError,
    UnsupportedInputError,
)
from .pipeline import ConvertOptions, ConvertResult, convert, convert_all
from .readings import Readings
from .reporting import Reporter
from .timeline import Timeline

__all__ = [
    "Block",
    "Chapter",
    "CommandFailedError",
    "ConvertOptions",
    "ConvertResult",
    "EngineNotReadyError",
    "EngineSettings",
    "Line",
    "MissingCommandError",
    "ReaderError",
    "Readings",
    "Reporter",
    "Timeline",
    "UnsupportedInputError",
    "__version__",
    "convert",
    "convert_all",
]
