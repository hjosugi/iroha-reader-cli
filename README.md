# iroha-reader-cli

iroha-reader-cli converts a document into audio plus a synced lyrics file.

- Input: `.md` / `.pdf` / `.txt`
- Output: one audio file (`.mp3` or `.wav`) plus subtitles
  (`.lrc` by default; `.srt` and `.vtt` via `--subs`)

Each line in the LRC has a start time. A music player can highlight
the current line while the audio plays. This is like an audiobook
with karaoke-style text.

Most LRC tools work the other way. They take audio and guess the
lyrics. iroha-reader-cli starts from text. So the timing is exact by design.
iroha-reader-cli makes the audio line by line. It measures each segment. Then
it joins them. So every timestamp matches the audio with no speech
recognition and no forced alignment.

## Engines and cost

Everything iroha-reader-cli needs is free of charge. The engines differ in
freedom and quality:

| Engine | Cost | Where it runs | Quality | Note |
| --- | --- | --- | --- | --- |
| `openjtalk` | free, open source | local, offline | good (Japanese) | auto default for Japanese |
| `piper` | free, open source (GPL-3.0) | local, offline | high (English + 30 languages) | auto default for non-Japanese when installed |
| `espeak` | free, open source | local, offline | basic | fallback for everything |
| `voicevox` | free | local server | high (Japanese) | start the VOICEVOX engine first. Publishing audio needs a credit line, check the VOICEVOX terms |
| `edge` | no charge | Microsoft online service | high | unofficial use of an online service. No guarantee. Opt-in only |

The default engine is `auto`. It picks `openjtalk` for Japanese
text, `piper` for other languages when installed, and `espeak` as
the fallback. All of them are fully free, open source, and offline.

## Requirements

- Linux (tested on Ubuntu 24.04)
- Python 3.11+
- `ffmpeg` and `ffprobe`

```sh
sudo apt install ffmpeg espeak-ng \
  open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
```

Optional, for neural quality English (and 30+ other languages):

```sh
pip install piper-tts
mkdir -p ~/.local/share/iroha-reader-cli/piper
python3 -m piper.download_voices en_US-lessac-medium \
  --download-dir ~/.local/share/iroha-reader-cli/piper
```

Piper is a separate GPL-3.0 project. iroha-reader-cli calls it as an
external command, like ffmpeg.

## Install

```sh
pip install .
# or, isolated:
pipx install .
```

## Usage

```sh
# Japanese markdown -> notes.mp3 + notes.lrc (next to the input)
# Uses Open JTalk when installed. Free, offline.
iroha-reader-cli notes.md

# High quality Japanese with a local VOICEVOX engine
# Start the VOICEVOX app or engine first (port 50021).
iroha-reader-cli notes.md --engine voicevox --speaker 3

# English pdf, wav output, custom output dir
iroha-reader-cli paper.pdf --format wav -o out/

# Force the basic offline engine
iroha-reader-cli notes.txt --engine espeak

# Check the line split first. No audio is made.
iroha-reader-cli notes.md --dry-run
```

List the VOICEVOX styles (id goes to `--speaker`):

```sh
curl -s http://127.0.0.1:50021/speakers | python3 -m json.tool
```

## Voice customization

Every engine takes voice settings. Negative values need the `=` form,
like `--edge-pitch=-20Hz`.

| Engine | Voice | Speed | Pitch | Volume |
| --- | --- | --- | --- | --- |
| openjtalk | `--ojt-voice file.htsvoice` | `--speed 1.5` | `--ojt-halftone 3.0` | `--ojt-volume-db=-6` |
| piper | `--piper-model en_US-amy-medium` | `--piper-length 1.2` (bigger = slower) | - | - |
| espeak | `--lang ja+f3` (variants: +f1..f5, +m1..m7) | `--wpm 220` | `--es-pitch 80` | `--es-amp 150` |
| voicevox | `--speaker 8` (style id) | `--vv-speed 1.2` | `--vv-pitch 0.05` | `--vv-volume 0.9` |
| edge | `--voice ja-JP-KeitaNeural` | `--rate +10%` | `--edge-pitch +20Hz` | `--edge-volume +20%` |

Extra knobs:
- voicevox: `--vv-intonation 1.3` makes the voice more expressive.
- openjtalk: any `.htsvoice` file works with `--ojt-voice`. The free
  MMDAgent "Mei" voices sound nicer than the apt default.
- voicevox style ids: `curl -s http://127.0.0.1:50021/speakers`.
- edge voices: `edge-tts --list-voices`.

## Choosing a speaker

List what each engine offers:

```sh
iroha-reader-cli --list-speakers --engine voicevox        # needs a running engine
iroha-reader-cli --list-speakers --engine openjtalk       # installed .htsvoice files
iroha-reader-cli --list-speakers --engine piper           # downloaded .onnx voices
iroha-reader-cli --list-speakers --engine espeak --lang ja
iroha-reader-cli --list-speakers --engine edge --lang ja
```

For voicevox, `--speaker` takes an id, a speaker name, or name:style:

```sh
iroha-reader-cli notes.md --engine voicevox --speaker 8
iroha-reader-cli notes.md --engine voicevox --speaker "Zundamon"
iroha-reader-cli notes.md --engine voicevox --speaker "Zundamon:Amaama"
```

## Reading dictionary (fix misreads)

TTS engines sometimes misread words. Give iroha-reader-cli a TSV file with
`word<TAB>reading` pairs. The reading changes only the spoken audio.
Subtitles keep the original text.

```sh
printf 'IIJ\tアイアイジェイ\nDWH\tデータウェアハウス\n' > readings.tsv
iroha-reader-cli notes.md --dict readings.tsv
```

Lines starting with `#` are comments. Longer words win.

## Config file

Save your favorite settings once. iroha-reader-cli reads
`~/.config/iroha-reader-cli/config.toml` when it exists. CLI flags always win
over the config file. Use `--config path.toml` for another file.

```toml
# ~/.config/iroha-reader-cli/config.toml
engine = "voicevox"
speaker = 8
vv-speed = 1.1
vv-intonation = 1.2
gap-ms = 150
subs = ["lrc", "srt"]
```

Keys are the long option names without the leading dashes.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--engine` | `auto` | `auto` / `openjtalk` / `espeak` / `voicevox` / `edge` |
| `--config` | auto | config file path |
| `--list-speakers` | off | list voices of the chosen engine and exit |
| `--name` | input name | output base name (one input only) |
| `--pages` | all | pdf page range: `3-10`, `5`, `3-` |
| `--dict` | none | reading dictionary TSV (word TAB reading) |
| `--bitrate` | `64k` | mp3 bitrate, like `128k` |
| `--loudnorm` | off | normalize loudness (ffmpeg loudnorm) |
| `--quiet` | off | no progress output |
| `--speaker` | `3` | voicevox style id |
| `--voicevox-url` | `http://127.0.0.1:50021` | voicevox engine url |
| `--ojt-dict` | apt path | open_jtalk dictionary directory |
| `--ojt-voice` | apt path | open_jtalk `.htsvoice` file |
| `--speed` | `1.0` | openjtalk speech rate |
| `--voice` | auto | edge voice. Auto picks Japanese or English by content |
| `--rate` | `+0%` | edge speech rate, like `+10%` or `-20%` |
| `--lang` | auto | espeak language, like `ja` or `en` |
| `--wpm` | `175` | espeak words per minute |
| `--format` | `mp3` | output audio format, `mp3` or `wav` |
| `--subs` | `lrc` | subtitle formats. Repeat to add: `--subs lrc --subs srt --subs vtt` |
| `--gap-ms` | `200` | silence between lines, in ms |
| `--max-chars` | `60` | max characters per LRC line |
| `--keep-code` | off | also read markdown code blocks |
| `--write-text` | off | also save the extracted lines as `.lines.txt` |
| `--dry-run` | off | print lines only |
| `--concurrency` | `4` | parallel edge requests |

## How the timing works

1. Extract plain text from the input file.
2. Split the text into short lines. Sentences first, then wrap long ones.
3. Synthesize one audio segment per line.
4. Measure each segment with `ffprobe`.
5. Join segments (plus small gaps) with `ffmpeg`.
6. The start time of line N is the sum of all earlier segments and gaps.

## Notes and limits

- The `edge` engine is free of charge but uses Microsoft's online
  service in an unofficial way. It may break or throttle at any
  time. Use the local engines when you need a guarantee.
- VOICEVOX itself is free. When you publish the audio, add a credit
  line like `VOICEVOX:Zundamon`. Check the official terms per
  character.
- PDF text extraction is basic. Multi-column layouts may come out in
  the wrong order. See `ISSUES.md`.
- Markdown code blocks are skipped by default. Use `--keep-code` to
  read them.
- Timestamps are line level. Word level (Enhanced LRC) is a
  planned feature. See `ISSUES.md`.

## Native build (single binary)

Build a standalone Linux executable. No Python needed on the target
machine:

```sh
./scripts/build-native.sh
# -> dist/iroha-reader-cli  (one file, x86-64 Linux)
```

The build runs inside a private venv under `build/`. Your system
Python stays clean.

The binary still calls the system commands at run time. Install
`ffmpeg` (always) and `espeak-ng` / `open_jtalk` / `piper` (when
used) on the target machine. Build on the oldest Linux you want to
support, since the glibc of the build machine sets the floor.

### AppImage

```sh
./scripts/build-appimage.sh
# -> dist/iroha-reader-cli-x86_64.AppImage
```

Run it like any AppImage:

```sh
chmod +x iroha-reader-cli-x86_64.AppImage
./iroha-reader-cli-x86_64.AppImage notes.md

# On systems without FUSE (containers, WSL, some servers):
./iroha-reader-cli-x86_64.AppImage --appimage-extract-and-run notes.md
```

The icon is a plain placeholder. Swap
`build/AppDir/iroha-reader-cli.png` in the build script when you
have a real one.

## License

MIT
