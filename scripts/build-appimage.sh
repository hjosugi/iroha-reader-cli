#!/usr/bin/env bash
# Build a Linux AppImage around the single-file binary.
#
# Needs curl for appimagetool on the first run. The AppImage still
# calls ffmpeg (and espeak-ng / open_jtalk / piper when used) on the
# target machine.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH=${ARCH:-x86_64}
./scripts/build-native.sh

APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp dist/iroha-reader-cli "$APPDIR/usr/bin/"

cat > "$APPDIR/AppRun" << 'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/iroha-reader-cli" "$@"
RUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/iroha-reader-cli.desktop" << 'DESK'
[Desktop Entry]
Type=Application
Name=iroha-reader-cli
Exec=iroha-reader-cli
Icon=iroha-reader-cli
Comment=Read documents out loud with synced subtitles
Categories=Utility;AudioVideo;
Terminal=true
DESK

if [ -f assets/icon.png ]; then
  cp assets/icon.png "$APPDIR/iroha-reader-cli.png"
else
  python3 scripts/make-icon.py "$APPDIR/iroha-reader-cli.png"
fi

TOOL=build/appimagetool
if [ ! -x "$TOOL" ]; then
  mkdir -p build
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$TOOL"
fi

# --appimage-extract-and-run also works on machines without FUSE.
OUT="dist/iroha-reader-cli-${ARCH}.AppImage"
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"

echo
echo "appimage: $OUT"
