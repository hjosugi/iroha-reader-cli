#!/usr/bin/env bash
# Check that a built executable really works: read a document into audio
# plus subtitles, and serve the reading room page.
#
#   ./scripts/smoke-test.sh dist/iroha-reader-cli
#
# Needs ffmpeg and espeak-ng on PATH (or, on Windows, espeak-ng where its
# installer puts it). Runs on Linux, macOS, and Git Bash on Windows.
set -euo pipefail
cd "$(dirname "$0")/.."

binary=${1:?usage: smoke-test.sh BINARY}
out=$(mktemp -d)
server_pid=""
cleanup() {
  if [ -n "$server_pid" ]; then kill "$server_pid" 2> /dev/null || true; fi
  rm -rf "$out"
}
trap cleanup EXIT

"$binary" --version

"$binary" examples/sample_en.txt -o "$out" --engine espeak --subs lrc,srt
test -s "$out/sample_en.mp3"
test -s "$out/sample_en.lrc"
test -s "$out/sample_en.srt"
head -n 3 "$out/sample_en.lrc"

# The reading room page ships inside the executable, not next to it.
port=$((20000 + RANDOM % 20000))
"$binary" --serve --port "$port" > "$out/serve.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$port/" -o "$out/page.html" 2> /dev/null; then
    break
  fi
  sleep 1
done
if ! grep -qi "<html" "$out/page.html" 2> /dev/null; then
  echo "error: the reading room page was not served" >&2
  cat "$out/serve.log" >&2
  exit 1
fi
echo "smoke test passed: $binary"
