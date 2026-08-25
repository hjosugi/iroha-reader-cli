"""Entry point for the PyInstaller build.

PyInstaller runs this file as a plain script, so the import has to be
absolute. `python -m iroha_reader_cli` uses __main__.py instead.
"""

from __future__ import annotations

import sys

from iroha_reader_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
