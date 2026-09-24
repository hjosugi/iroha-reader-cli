#!/usr/bin/env bash
# Build a single-file executable with Nuitka instead of PyInstaller.
#
# Nuitka compiles the Python code to C and links it against the
# interpreter, so the program itself starts faster than the PyInstaller
# build, which imports everything from an unpacked archive. Both still
# unpack to a temporary directory on each start. Same run-time needs as
# the PyInstaller build: ffmpeg, plus the engine you use.
#
# Needs a C compiler. On Linux the glibc of the build machine sets the
# floor, as with build-native.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv > /dev/null; then
  echo "error: uv is required. Install it with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

name=iroha-reader-cli-nuitka
uv run --group nuitka --no-group dev python -m nuitka \
  --onefile \
  --assume-yes-for-downloads \
  --output-dir=build/nuitka \
  --output-filename="$name" \
  --include-package=iroha_reader_cli \
  --include-package-data=iroha_reader_cli \
  --include-package-data=edge_tts \
  scripts/entrypoint.py

mkdir -p dist
binary="dist/$name"
if [ -f "build/nuitka/$name.exe" ]; then binary="$binary.exe"; fi
cp "build/nuitka/$(basename "$binary")" "$binary"
echo
echo "binary: $binary"
"$binary" --version
