"""Run the tool as a module: python -m iroha_reader_cli."""

from __future__ import annotations

import sys

from iroha_reader_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
