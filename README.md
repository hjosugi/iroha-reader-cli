# iroha-reader-cli

[![CI](https://github.com/hjosugi/iroha-reader-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hjosugi/iroha-reader-cli/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Read a document out loud and get the subtitles for free.

- **In:** `.md` / `.pdf` / `.txt`
- **Out:** one audio file (`.mp3` or `.wav`) plus timed text
  (`.lrc` by default, `.srt` and `.vtt` on request)

```sh
iroha-reader-cli notes.md
# notes.mp3 + notes.lrc, next to the input
```

Every line in the LRC carries a start time, so a music player can
highlight the line that is playing. It is an audiobook with karaoke
text:

```lrc
[ti:notes]
[re:iroha-reader-cli]
[length:00:12.63]

[00:00.00]This is a small English sample for iroha-reader-cli.
[00:03.10]It shows how plain text becomes audio and an LRC file.
[00:06.98]Each sentence gets its own timestamp.
[00:09.69]Numbers like 3.14 stay in one line.
```

## Why the timing is exact

Most LRC tools work the other way around: they take audio and guess
where the words are. This one starts from the text.

Each line is synthesized on its own, measured with `ffprobe`, and only
then are the segments joined with exactly the gaps the timeline
assumes. No speech recognition, no forced alignment, nothing to drift.
The test suite checks that claim on every run.

## Engines

Everything here is free of charge. The engines differ in freedom and
in quality:

| Engine | Cost | Where it runs | Quality | Note |
| --- | --- | --- | --- | --- |
| `openjtalk` | free, open source | local, offline | good (Japanese) | `auto` picks this for Japanese |
| `piper` | free, open source (GPL-3.0) | local, offline | high (English + 30 languages) | `auto` picks this for other languages when installed |
| `espeak` | free, open source | local, offline | basic | always available, the fallback |
| `voicevox` | free | local server | high (Japanese) | start the VOICEVOX engine first. Published audio needs a credit line -- check the terms |
| `edge` | no charge | Microsoft online service | high | unofficial use of an online service. No guarantee. Opt in with `--engine edge` |

`--engine auto` is the default: Open JTalk for Japanese, Piper for
everything else, espeak-ng when neither is installed. All three are
free, open source, and offline.

## Install

Requirements: Linux, Python 3.11+, and `ffmpeg`.

```sh
# the tool itself
uv tool install git+https://github.com/hjosugi/iroha-reader-cli
# or: pipx install git+https://github.com/hjosugi/iroha-reader-cli

# ffmpeg, plus the two offline engines
sudo apt install ffmpeg espeak-ng \
  open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
```

Neural quality English (and 30+ other languages) is one more step:

```sh
uv tool install piper-tts        # or: pip install piper-tts
mkdir -p ~/.local/share/iroha-reader-cli/piper
python3 -m piper.download_voices en_US-lessac-medium \
  --download-dir ~/.local/share/iroha-reader-cli/piper
```

Piper is a separate GPL-3.0 project. iroha-reader-cli calls it as an
external command, the same way it calls ffmpeg, so this package stays
MIT.

Prefer a single file with no Python at all? See
[Native builds](#native-builds).

## Usage

```sh
# Japanese markdown -> notes.mp3 + notes.lrc (Open JTalk, offline)
iroha-reader-cli notes.md

# English pdf -> wav in another directory, with SRT subtitles
iroha-reader-cli paper.pdf --format wav -o out/ --subs lrc,srt

# Only pages 3 to 10 of a pdf
iroha-reader-cli book.pdf --pages 3-10

# High quality Japanese from a running VOICEVOX engine (port 50021)
iroha-reader-cli notes.md --engine voicevox --speaker "Zundamon"

# Check the line split first. No audio is made.
iroha-reader-cli notes.md --dry-run
```

Several files at once work too; each one becomes its own audio file.

## Voice customization

Every engine takes voice settings. Negative values need the `=` form,
like `--edge-pitch=-20Hz`.

| Engine | Voice | Speed | Pitch | Volume |
| --- | --- | --- | --- | --- |
| openjtalk | `--ojt-voice file.htsvoice` | `--speed 1.5` | `--ojt-halftone 3.0` | `--ojt-volume-db=-6` |
| piper | `--piper-model en_US-amy-medium` | `--piper-length 1.2` (bigger is slower) | - | - |
| espeak | `--lang ja+f3` (variants: `+f1..f5`, `+m1..m7`) | `--wpm 220` | `--es-pitch 80` | `--es-amp 150` |
| voicevox | `--speaker 8` | `--vv-speed 1.2` | `--vv-pitch 0.05` | `--vv-volume 0.9` |
| edge | `--voice ja-JP-KeitaNeural` | `--rate +10%` | `--edge-pitch +20Hz` | `--edge-volume +20%` |

Extras: `--vv-intonation 1.3` makes VOICEVOX more expressive, and any
`.htsvoice` file works with `--ojt-voice` (the free MMDAgent "Mei"
voices sound nicer than the apt default).

## Choosing a speaker

```sh
iroha-reader-cli --list-speakers --engine voicevox     # needs a running engine
iroha-reader-cli --list-speakers --engine openjtalk    # installed .htsvoice files
iroha-reader-cli --list-speakers --engine piper        # downloaded .onnx voices
iroha-reader-cli --list-speakers --engine espeak --lang ja
iroha-reader-cli --list-speakers --engine edge --lang ja
```

For VOICEVOX, `--speaker` takes an id, a speaker name, or `name:style`:

```sh
iroha-reader-cli notes.md --engine voicevox --speaker 8
iroha-reader-cli notes.md --engine voicevox --speaker "Zundamon"
iroha-reader-cli notes.md --engine voicevox --speaker "Zundamon:Amaama"
```

Piper voice samples: <https://rhasspy.github.io/piper-samples/>.

## Reading dictionary (fix misreads)

TTS engines mangle acronyms and names. Give the tool a TSV file of
`word<TAB>reading` pairs. The reading changes the audio only -- the
subtitles keep the original text.

```sh
printf 'IIJ\tアイアイジェイ\nDWH\tデータウェアハウス\n' > readings.tsv
iroha-reader-cli notes.md --dict readings.tsv
```

Lines starting with `#` are comments. Longer words win.

## Config file

Save your favourite settings once, in
`~/.config/iroha-reader-cli/config.toml`. Keys are the long option
names without the dashes. Command line flags always win.

```toml
engine = "voicevox"
speaker = 8
vv-speed = 1.1
vv-intonation = 1.2
gap-ms = 150
subs = ["lrc", "srt"]
```

Use `--config other.toml` to point somewhere else.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--engine` | `auto` | `auto` / `openjtalk` / `piper` / `espeak` / `voicevox` / `edge` |
| `-o`, `--outdir` | next to the input | output directory |
| `--name` | the input name | output base name (one input file only) |
| `--config` | `~/.config/iroha-reader-cli/config.toml` | config file |
| `--list-speakers` | off | list the voices of the chosen engine and exit |
| `--format` | `mp3` | `mp3` or `wav` |
| `--bitrate` | `64k` | mp3 bitrate, like `128k` |
| `--loudnorm` | off | normalize loudness (ffmpeg `loudnorm`) |
| `--subs` | `lrc` | subtitle formats: `--subs lrc,srt,vtt` |
| `--gap-ms` | `200` | silence between lines, in ms |
| `--max-chars` | `60` | max characters per subtitle line |
| `--pages` | all | pdf page range: `3-10`, `5`, `3-` |
| `--dict` | none | reading dictionary TSV (word TAB reading) |
| `--jobs` | `4` | lines synthesized at once by the local engines |
| `--keep-code` | off | read markdown code blocks out loud too |
| `--write-text` | off | also save the lines as `.lines.txt` |
| `--dry-run` | off | print the lines and exit |
| `-q`, `--quiet` | off | errors only |
| `--concurrency` | `4` | parallel requests for the `edge` engine |

Engine specific flags are listed under `--help`.

## Use it as a library

The command line is a thin layer over one function:

```python
from pathlib import Path
from iroha_reader_cli import ConvertOptions, EngineSettings, convert

result = convert(
    Path("notes.md"),
    ConvertOptions(subtitle_formats=("lrc", "srt"), gap_ms=150),
    EngineSettings(requested="espeak", jobs=4),
)
print(result.audio, result.timeline.total)
```

Errors are `ReaderError` subclasses, so a missing engine or a broken
file is something you can catch.

## Native builds

A single executable, with Python bundled in:

```sh
./scripts/build-native.sh      # -> dist/iroha-reader-cli
./scripts/build-appimage.sh    # -> dist/iroha-reader-cli-x86_64.AppImage
```

Both are attached to every [release](https://github.com/hjosugi/iroha-reader-cli/releases).

```sh
chmod +x iroha-reader-cli-x86_64.AppImage
./iroha-reader-cli-x86_64.AppImage notes.md

# without FUSE (containers, WSL, some servers):
./iroha-reader-cli-x86_64.AppImage --appimage-extract-and-run notes.md
```

The binary still calls `ffmpeg` at run time, plus `espeak-ng`,
`open_jtalk`, or `piper` for the engine you use. Build on the oldest
Linux you want to support: the glibc of the build machine sets the
floor.

## Development

```sh
uv sync              # create .venv and install everything
uv run pytest        # 97 tests, about two seconds
uv run ruff check .
uv run mypy
```

`uv run pytest -m "not slow"` skips the tests that need ffmpeg and
espeak-ng. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Notes and limits

- The `edge` engine is free of charge but uses a Microsoft online
  service in an unofficial way. It can throttle or break at any time.
  Use a local engine when you need a guarantee.
- VOICEVOX itself is free. When you publish the audio, add a credit
  line such as `VOICEVOX:ずんだもん`, and check the terms of the
  character you used.
- PDF extraction is basic. Multi-column layouts can come out in the
  wrong order ([#3](https://github.com/hjosugi/iroha-reader-cli/issues/3)).
- Timestamps are line level. Word level (Enhanced LRC) is
  [#1](https://github.com/hjosugi/iroha-reader-cli/issues/1).
- Piper has no official Japanese voice, so Japanese stays on Open
  JTalk or VOICEVOX.

## License

MIT. See [LICENSE](LICENSE).

Piper, VOICEVOX, Open JTalk, espeak-ng, and ffmpeg keep their own
licenses; this tool only calls them.
