#!/usr/bin/env bash
# Compare single-file builds: size on disk and start-up time.
#
#   ./scripts/compare-builds.sh dist/iroha-reader-cli dist/iroha-reader-cli-nuitka
#
# Start-up is the median wall time of `--version` over several runs,
# after one warm-up run each, so every build starts from a warm disk
# cache. Prints a Markdown table.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -lt 1 ]; then
  echo "usage: compare-builds.sh BINARY..." >&2
  exit 2
fi

python3 - "$@" << 'PY'
import os
import statistics
import subprocess
import sys
import time

RUNS = 15


def startup(binary: str) -> float:
    subprocess.run([binary, "--version"], check=True, capture_output=True)
    times = []
    for _ in range(RUNS):
        began = time.perf_counter()
        subprocess.run([binary, "--version"], check=True, capture_output=True)
        times.append(time.perf_counter() - began)
    return statistics.median(times)


print("| build | size | start-up (median of %d) |" % RUNS)
print("| --- | ---: | ---: |")
for binary in sys.argv[1:]:
    size = os.path.getsize(binary) / 1_000_000
    print(f"| `{os.path.basename(binary)}` | {size:.1f} MB | {startup(binary) * 1000:.0f} ms |")
PY
