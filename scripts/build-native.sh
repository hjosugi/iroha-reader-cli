#!/usr/bin/env bash
# Build a single-file Linux binary with PyInstaller.
#
# The binary bundles Python and the two Python dependencies. It still
# calls ffmpeg at run time, plus espeak-ng / open_jtalk / piper when
# those engines are used. Build on the oldest Linux you want to
# support: the glibc of the build machine sets the floor.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv > /dev/null; then
  echo "error: uv is required. Install it with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

uv run --group build --no-group dev pyinstaller \
  --onefile --clean --noconfirm \
  --name iroha-reader-cli \
  --distpath dist --workpath build/pyinstaller --specpath build \
  --collect-all edge_tts \
  scripts/entrypoint.py

echo
echo "binary: dist/iroha-reader-cli"
dist/iroha-reader-cli --version
