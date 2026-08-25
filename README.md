# iroha-reader-cli

[![CI](https://github.com/hjosugi/iroha-reader-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/hjosugi/iroha-reader-cli/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Read a document out loud and get the subtitles for free.

- **In:** `.md` / `.epub` / `.pdf` / `.txt`, or `-` for stdin
- **Out:** one audio file (`.mp3` or `.wav`) plus timed text
  (`.lrc` by default, `.srt` and `.vtt` on request), with chapters
  from the headings

```sh
iroha-reader-cli notes.md      # or just: irh notes.md
# notes.mp3 + notes.lrc, next to the input

iroha-reader-cli --serve
# ...or drop a file on a page and listen to it there
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

## The reading room

`--serve` opens one page on this machine -- it calls itself
**iroha-reader**, since there is no command line on it. Drop a document on it and
it comes back read out loud, with the text keeping time and every
line clickable:

```sh
iroha-reader-cli --serve
# reading room: http://127.0.0.1:8765/
```

![The web UI: a document converted, with the current line highlighted](docs/web-ui.png)

It is the standard library only, it binds to localhost, and the files
live in a temporary directory that goes away when you stop the
server. `--port`, `--host`, and `--no-browser` are there if you need
them.

## Word level timing

`--lrc-style word` adds a timestamp to every word, which is what
karaoke players read as Enhanced LRC. WebVTT gets the same treatment
as inline cue timestamps:

```sh
iroha-reader-cli notes.md --engine edge --lrc-style word --subs lrc,vtt
```

```lrc
[00:00.00]<00:00.10>This <00:00.35>is <00:00.46>a <00:00.54>small <00:00.88>English sample.
[00:04.09]<00:04.19>It <00:04.36>shows <00:04.61>how <00:04.74>plain <00:05.05>text becomes audio.
```

It works for Japanese too, where the service does the tokenizing:

```lrc
[00:00.00]<00:00.16>これ<00:00.39>は<00:00.54>テスト<00:00.96>です。
```

This needs `--engine edge`: the service reports where each word falls,
and no local engine does. Asking for it with a local engine is an
error rather than a guess, because guessed timestamps are worse than
none.

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

Requirements: Linux, Python 3.11+, and `ffmpeg`. `poppler-utils` is
worth adding if you read PDFs.

```sh
# the tool itself (installs both `iroha-reader-cli` and the short `irh`)
uv tool install git+https://github.com/hjosugi/iroha-reader-cli
# or: pipx install git+https://github.com/hjosugi/iroha-reader-cli

# ffmpeg, plus the two offline engines
sudo apt install ffmpeg espeak-ng poppler-utils \
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

# An epub, one audio file per chapter
iroha-reader-cli novel.epub --split-by-heading 1

# High quality Japanese from a running VOICEVOX engine (port 50021)
iroha-reader-cli notes.md --engine voicevox --speaker "Zundamon"

# Check the line split first. No audio is made.
iroha-reader-cli notes.md --dry-run

# Straight from a pipe. --type says how to read it (md, txt, or pdf)
pandoc report.docx -t markdown | iroha-reader-cli - --name report
```

Several files at once work too; each one becomes its own audio file.
With `-`, the output lands in the current directory and is called
`stdin.*` unless `--name` says otherwise.

## Voice customization

Every engine takes voice settings. Negative values need the `=` form,
like `--edge-pitch=-20Hz`.

| Engine | Voice | Speed | Pitch | Volume |
| --- | --- | --- | --- | --- |
| openjtalk | `--ojt-voice file.htsvoice` | `--speed 1.5` | `--ojt-halftone 3.0` | `--ojt-volume-db=-6` |
| piper | `--piper-model en_US-amy-medium` | `--speed 1.5`, or `--piper-length 1.2` (bigger is slower) | - | - |
| espeak | `--lang ja+f3` (variants: `+f1..f5`, `+m1..m7`) | `--speed 1.5`, or `--wpm 220` | `--es-pitch 80` | `--es-amp 150` |
| voicevox | `--speaker 8` | `--speed 1.5`, or `--vv-speed 1.2` | `--vv-pitch 0.05` | `--vv-volume 0.9` |
| edge | `--voice ja-JP-KeitaNeural` | `--speed 1.5`, or `--rate +10%` | `--edge-pitch +20Hz` | `--edge-volume +20%` |

`--speed 1.3` works with every engine: each one is told in its own
units (words per minute, length scale, speedScale, a percentage), and
the engine specific flag above wins when you set it.

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

### Nicer Japanese voices for Open JTalk

The apt voice (`nitech-jp-atr503-m001`) is the flattest thing in the
box. MMDAgent's free "Mei" and "Takumi" voices sound considerably
better and are not packaged in Debian or Ubuntu:

```sh
mkdir -p ~/.local/share/iroha-reader-cli/hts-voice
curl -L -o /tmp/mmdagent.zip "https://sourceforge.net/projects/mmdagent/files/MMDAgent_Example/MMDAgent_Example-1.8/MMDAgent_Example-1.8.zip/download"
unzip -j /tmp/mmdagent.zip 'MMDAgent_Example-1.8/Voice/*/*.htsvoice' \
  -d ~/.local/share/iroha-reader-cli/hts-voice

iroha-reader-cli notes.md --ojt-voice mei_happy
```

Anything in that directory can be named instead of pathed
(`mei_normal`, `takumi_sad`, ...), `--list-speakers --engine
openjtalk` lists what you have, and if the apt voice is missing a Mei
voice is preferred over the rest.

The Mei and Takumi voices are CC BY 3.0 (Nagoya Institute of
Technology). Credit them if you publish the audio.

## PDF text

Two backends, picked by `--pdf-backend`:

| Backend | Needs | Notes |
| --- | --- | --- |
| `pdftotext` | `poppler-utils` | joins words hyphenated across lines, normalizes ligatures, better at multi-column reading order |
| `pypdf` | nothing extra | pure Python fallback, returns the text in the order the file stores it |

`auto` (the default) uses `pdftotext` when poppler is installed. It is
worth having: a paper that pypdf reads as `cosine- similarity` and
`out- perform` comes out as real words, which is the difference
between a listenable paragraph and a stuttering one.

```sh
sudo apt install poppler-utils
```

## Reading dictionary (fix misreads)

TTS engines mangle acronyms and names. Give the tool a TSV file of
`word<TAB>reading` pairs. The reading changes the audio only -- the
subtitles keep the original text.

```sh
printf 'IIJ\tアイアイジェイ\nDWH\tデータウェアハウス\n' > readings.tsv
iroha-reader-cli notes.md --dict readings.tsv
```

Lines starting with `#` are comments. Longer words win.

## Shell completion

The scripts are generated from the parser, so they cannot go stale:

```sh
# fish
irh --completion fish > ~/.config/fish/completions/irh.fish

# bash
irh --completion bash | sudo tee /etc/bash_completion.d/irh

# zsh (with ~/.zfunc in $fpath)
irh --completion zsh > ~/.zfunc/_irh
```

`irh --engine <TAB>` then offers the engines, `--subs <TAB>` the
subtitle formats, and everything else completes file names.

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

### Profiles

One file can hold several setups. Reading a paper and falling asleep
to one are not the same settings:

```toml
gap-ms = 200

[profile.study]
engine = "voicevox"
vv-speed = 1.3
subs = ["lrc", "srt"]

[profile.relax]
engine = "openjtalk"
speed = 0.9
```

```sh
iroha-reader-cli notes.md --profile study
```

Profile keys win over the top level ones, and the command line wins
over both. Naming a profile that is not there lists the ones that
are.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--completion` | none | print a completion script: `bash`, `zsh`, `fish` |
| `--serve` | off | open the local web page instead of converting a file |
| `--port` | `8765` | port for `--serve` |
| `--host` | `127.0.0.1` | address for `--serve` |
| `--no-browser` | off | do not open a browser for `--serve` |
| `--speed` | `1.0` | speech rate for any engine, 0.5 slow to 2.0 fast |
| `--engine` | `auto` | `auto` / `openjtalk` / `piper` / `espeak` / `voicevox` / `edge` |
| `-o`, `--outdir` | next to the input | output directory |
| `--name` | the input name | output base name (one input file only) |
| `--config` | `~/.config/iroha-reader-cli/config.toml` | config file |
| `--profile` | none | use a `[profile.NAME]` table from the config file |
| `--list-speakers` | off | list the voices of the chosen engine and exit |
| `--format` | `mp3` | `mp3` or `wav` |
| `--bitrate` | `64k` | mp3 bitrate, like `128k` |
| `--loudnorm` | off | normalize loudness (ffmpeg `loudnorm`) |
| `--subs` | `lrc` | subtitle formats: `--subs lrc,srt,vtt` |
| `--chapter-level` | `2` | headings this deep or shallower become chapters |
| `--no-chapters` | off | do not write chapters into the mp3 |
| `--split-by-heading` | off | one audio file per heading of that level |
| `--lrc-style` | `line` | `word` adds a timestamp per word (Enhanced LRC, karaoke VTT). Needs `--engine edge` |
| `--gap-ms` | `200` | silence between lines, in ms |
| `--max-chars` | `60` | max characters per subtitle line |
| `--type` | `md` | how to read stdin when the input is `-`: `md`, `txt`, `pdf`, `epub` |
| `--pdf-backend` | `auto` | `auto` / `pdftotext` / `pypdf` |
| `--pages` | all | pdf page range: `3-10`, `5`, `3-` |
| `--dict` | none | reading dictionary TSV (word TAB reading) |
| `--jobs` | `4` | lines synthesized at once by the local engines. Piper loads its model per line, so lower it if memory is tight |
| `--no-cache` | off | synthesize every line again |
| `--cache-dir` | `~/.cache/iroha-reader-cli/segments` | where segments are cached |
| `--cache-max-mb` | `2048` | how much cache to keep; `0` keeps everything |
| `--clear-cache` | off | delete the cached segments and exit |
| `--keep-code` | off | read markdown code blocks out loud too |
| `--write-text` | off | also save the lines as `.lines.txt` |
| `--json` | off | print the result as JSON on stdout |
| `--dry-run` | off | print the lines and exit |
| `-q`, `--quiet` | off | errors only |
| `--concurrency` | `4` | parallel requests for the `edge` engine |
| `--min-interval-ms` | `0` | least time between `edge` requests |

Engine specific flags are listed under `--help`.

## epub

An epub is a zip of XHTML with a spine that says in which order to
read it. That is all this needs: no extra package, and the `<h1>`
headings become chapters the same way markdown ones do.

```sh
iroha-reader-cli novel.epub                       # one file, chapter marks
iroha-reader-cli novel.epub --split-by-heading 1  # one file per chapter
iroha-reader-cli novel.epub --dry-run | head      # see what it will read
```

Scripts, styles, and `<title>` tags are skipped; entities and line
breaks come out as text. DRM protected files are not supported and
never will be.

## Chapters

Markdown headings become real chapters in the mp3, so a player can
jump between them:

```sh
iroha-reader-cli book.md
#   chapters: 4
```

```
$ ffprobe -show_chapters book.mp3
[CHAPTER] 0.000 -> 17.720  はじめに
[CHAPTER] 17.720 -> 36.549  第一章 出会い
...
```

`--chapter-level N` decides how deep to go (2 by default: `#` and
`##`), and `--no-chapters` leaves the tags alone. WAV has nowhere to
put them, so it never gets any.

One file per chapter instead of one long one:

```sh
iroha-reader-cli book.md --split-by-heading 2
# book-01-はじめに.mp3 + .lrc
# book-02-第一章-出会い.mp3 + .lrc
# ...
```

Each part gets its own audio and its own subtitles, timed from zero.
Splitting after a normal run costs nothing extra: the segments are
already cached.

## Does it scale to a book

Frankenstein from Project Gutenberg, on a laptop:

```sh
iroha-reader-cli frankenstein.epub --split-by-heading 2 --engine espeak --jobs 8
```

9290 lines, 33 chapters, 12.4 hours of audio, 2 minutes of work. Each
chapter comes with its own LRC, and the `[length:]` in each one
matches its mp3 to the hundredth of a second.

A neural voice is slower per line -- that is the trade -- but the
cache means you pay it once.

## The segment cache

Synthesis is the slow part. Every line is stored under a hash of the
text and of every engine setting that changes how it sounds, so a
re-run only speaks what actually changed:

```
$ iroha-reader-cli notes.md
  lines: 240
  engine: piper (en_US-lessac-medium)
  cache: 236/240 lines reused
```

A line that appears twice in one document is spoken once, even on the
first run. Cached segments live in
`~/.cache/iroha-reader-cli/segments`, and the cache keeps itself
under 2 GB by dropping whatever has gone longest unused:

```sh
irh --clear-cache                 # delete it all, report what was freed
irh notes.md --no-cache           # ignore the cache for this run
irh notes.md --cache-max-mb 0     # let it grow without limit
irh notes.md --cache-dir /tmp/cache
```

A twelve hour audiobook is about 2 GB of segments, so one book fills
it. That is the point of the limit.

Changing the voice, the speed, the pitch, or the voice file itself
misses the cache on purpose. `--gap-ms`, `--bitrate`, and `--loudnorm`
do not: they only affect the join, so they never cost a re-synthesis.

## JSON out

`--json` prints the whole result on stdout, so the rest of a pipeline
can have it. Progress stays on stderr, so the JSON is clean:

```sh
irh notes.md --json -q | jq '.[0].chapters'
```

```json
[
  { "title": "Opening", "start": 0.0, "end": 17.72 },
  { "title": "Chapter One", "start": 17.72, "end": 36.55 }
]
```

Each result carries the paths it wrote, the chapters, and every line
with its start and end (and its words, with `--lrc-style word`). One
object per output file, so `--split-by-heading` gives you one per
chapter.

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
./scripts/build-native.sh                # -> dist/iroha-reader-cli
./scripts/build-appimage.sh              # -> dist/iroha-reader-cli-x86_64.AppImage
ARCH=aarch64 ./scripts/build-appimage.sh # on an arm64 machine
```

Every [release](https://github.com/hjosugi/iroha-reader-cli/releases)
carries both, for x86-64 and arm64.

```sh
chmod +x iroha-reader-cli-x86_64.AppImage
./iroha-reader-cli-x86_64.AppImage notes.md

# without FUSE (containers, WSL, some servers):
./iroha-reader-cli-x86_64.AppImage --appimage-extract-and-run notes.md
```

The binary still calls `ffmpeg` at run time, plus `espeak-ng`,
`open_jtalk`, or `piper` for the engine you use. The released ones are
built inside `manylinux_2_28`, so they need only glibc 2.14: Ubuntu
18.04, Debian 10, and RHEL 8 onwards. Building them yourself puts the
floor at your own machine's glibc.

## Development

```sh
uv sync              # create .venv and install everything
uv run pytest        # 302 tests, about eight seconds
uv run ruff check .
uv run mypy
```

`uv run pytest -m "not slow"` skips the tests that need ffmpeg and
espeak-ng. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Notes and limits

- The `edge` engine is free of charge but uses a Microsoft online
  service in an unofficial way. It can throttle or break at any time.
  Use a local engine when you need a guarantee. When it does throttle,
  the run slows itself down, says so, and the final error names the
  cause; `--min-interval-ms 300` is the usual fix.
- VOICEVOX itself is free. When you publish the audio, add a credit
  line such as `VOICEVOX:ずんだもん`, and check the terms of the
  character you used.
- PDF extraction is only as good as the backend. Install
  `poppler-utils` for the better one; see [PDF text](#pdf-text).
- Piper has no official Japanese voice, so Japanese stays on Open
  JTalk or VOICEVOX.

## License

MIT. See [LICENSE](LICENSE).

Piper, VOICEVOX, Open JTalk, espeak-ng, and ffmpeg keep their own
licenses; this tool only calls them.
