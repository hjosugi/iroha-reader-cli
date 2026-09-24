#!/usr/bin/env bash
# Build a single-file executable with PyInstaller, on Linux, macOS, or
# Windows (from Git Bash). It is built for the machine it runs on.
#
# The binary bundles Python and the two Python dependencies. It still
# calls ffmpeg at run time, plus espeak-ng / open_jtalk / piper when
# those engines are used. On Linux, build on the oldest system you want
# to support: the glibc of the build machine sets the floor.
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
  --collect-data iroha_reader_cli \
  scripts/entrypoint.py

binary=dist/iroha-reader-cli
if [ -f "$binary.exe" ]; then binary="$binary.exe"; fi
echo
echo "binary: $binary"
"$binary" --version
