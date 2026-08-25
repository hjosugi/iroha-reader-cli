#!/usr/bin/env bash
# Build a single-file Linux binary with PyInstaller.
# Uses a private venv under build/. Your system Python stays clean.
# The binary still needs ffmpeg (and espeak-ng / open_jtalk / piper
# when used) on the target machine.
set -eu
cd "$(dirname "$0")/.."

VENV=build/venv
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" || {
    echo "error: python3 -m venv failed. Install it first:" >&2
    echo "  sudo apt install python3-venv" >&2
    exit 1
  }
fi
"$VENV/bin/pip" install --quiet --upgrade pip pyinstaller .

"$VENV/bin/python" -m PyInstaller --onefile --clean \
  --name iroha-reader-cli \
  --collect-all edge_tts \
  iroha_reader_cli/__main__.py

echo
echo "binary: dist/iroha-reader-cli"
