#!/usr/bin/env bash
# Build a Linux AppImage. Runs the PyInstaller build first.
# The AppImage still needs ffmpeg (and espeak-ng / open_jtalk / piper
# when used) on the target machine.
set -eu
cd "$(dirname "$0")/.."

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

# Simple placeholder icon. Replace with a real icon later.
ffmpeg -y -v error -f lavfi -i color=c=0x6B4FA0:s=256x256 -frames:v 1 \
  "$APPDIR/iroha-reader-cli.png"

TOOL=build/appimagetool
if [ ! -x "$TOOL" ]; then
  curl -L -o "$TOOL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi

# --appimage-extract-and-run works on machines without FUSE.
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" \
  dist/iroha-reader-cli-x86_64.AppImage

echo
echo "appimage: dist/iroha-reader-cli-x86_64.AppImage"
