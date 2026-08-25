# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Sentences no longer break at an abbreviation. `Dr. Smith went home.`
  was three lines (`Dr.`, `Smith went home.`), and so were initials
  like `J. R. R. Tolkien` and references like `see fig. 3`. A full
  stop after a known abbreviation or a single letter, or before a
  lower case word, no longer ends a sentence.
- A closing quote or bracket stays with the sentence it closes.
  `「こんにちは。」` used to leave `」` stranded at the start of the
  next line, and `he said "stop." Then...` did not split at all.

## [0.11.0] - 2026-08-26

### Added

- `irh` as a second name for the command, for the many times a day
  you type it. `--help` shows whichever name you used.
- The cache keeps itself under a size limit (2 GB by default,
  `--cache-max-mb`), dropping whatever has gone longest unused. A
  cache hit counts as use, so what you actually listen to stays.
- `--speed` now works with every engine, not just Open JTalk: each one
  is told in its own units (words per minute, length scale,
  speedScale, a percentage). The engine specific flags still win when
  you set them.

### Changed

- The web page calls itself iroha-reader rather than
  iroha-reader-cli. There is no command line on it.

- Segment lengths are read out of the wav header instead of by
  running ffprobe once per line. A whole novel (9290 lines) used to
  spend six minutes measuring after one minute of synthesis; the
  measuring is now a fifth of a second. mp3 segments still go through
  ffprobe.
- The progress counter only rewrites one line when it is talking to a
  terminal. In a log file or a pipe it prints ten lines for the whole
  run instead of tens of thousands of carriage returns.

## [0.10.0] - 2026-08-26

### Added

- arm64 Linux binaries. Every release now carries a plain binary and
  an AppImage for both x86-64 and aarch64, each smoke tested on its
  own architecture before publishing
  ([#11](https://github.com/hjosugi/iroha-reader-cli/issues/11)).

- `--serve`: a local web page. Drop a document on it, get the audio
  back with the text highlighting itself line by line, every line
  clickable to jump there, and the mp3 and subtitles a click away.
  Standard library only, bound to localhost, files kept in a
  temporary directory for the life of the server
  ([#2](https://github.com/hjosugi/iroha-reader-cli/issues/2)).

### Fixed

- The single file builds no longer break the commands they call. A
  PyInstaller build unpacks its own libstdc++ and points
  `LD_LIBRARY_PATH` at it; ffmpeg and espeak-ng inherited that and
  failed to load with `GLIBCXX_... not found` whenever the system
  libraries were newer than the build machine's. External commands now
  get the environment the binary was started with.

### Changed

- The binaries are built inside manylinux_2_28, which drops the glibc
  floor from 2.39 to 2.14 -- they now run on distributions from
  Ubuntu 18.04 and RHEL 8 onwards
  ([#11](https://github.com/hjosugi/iroha-reader-cli/issues/11)).
- The plain binary asset is named after its architecture:
  `iroha-reader-cli-linux-x86_64`, `iroha-reader-cli-linux-aarch64`.

## [0.9.0] - 2026-08-26

### Added

- `-` as an input reads the document from stdin, with `--type
  {md,txt,pdf}` in place of the missing file suffix. The output goes
  to the current directory as `stdin.*`, or wherever `--name` and
  `-o` say ([#12](https://github.com/hjosugi/iroha-reader-cli/issues/12)).
- `--profile NAME` reads a `[profile.NAME]` table from the config
  file, so one file can hold several setups. Profile keys beat the
  top level ones, the command line beats both
  ([#10](https://github.com/hjosugi/iroha-reader-cli/issues/10)).
- A segment cache. Each line is stored under a hash of the text and
  of every engine setting that changes how it sounds, so editing one
  paragraph of a long document re-synthesizes one paragraph. A line
  that repeats within a document is spoken once even on the first
  run. `--no-cache`, `--cache-dir`, and `--clear-cache` are there when
  you want none of it
  ([#4](https://github.com/hjosugi/iroha-reader-cli/issues/4)).
- `--pdf-backend {auto,pdftotext,pypdf}`. `auto` uses `pdftotext` when
  poppler is installed: it joins words hyphenated across a line break,
  normalizes ligatures, and reads multi-column pages in a better
  order. pypdf stays the fallback and needs nothing extra
  ([#3](https://github.com/hjosugi/iroha-reader-cli/issues/3)).
- `--lrc-style word`: a timestamp for every word, as Enhanced LRC
  (`<mm:ss.xx>` inside the line) and as inline WebVTT cue timestamps.
  The times come from the edge service's own word boundary events, so
  they are measured rather than guessed; asking for them with a local
  engine is an error. Works for Japanese as well as English
  ([#1](https://github.com/hjosugi/iroha-reader-cli/issues/1)).
- The edge engine now handles throttling instead of grinding through
  it: three failures in a row slow the whole run down (announced
  once), `--min-interval-ms` spaces requests out, and the error that
  ends a run names the cause -- throttling, network, or TLS -- with
  the fix for that cause
  ([#6](https://github.com/hjosugi/iroha-reader-cli/issues/6)).
- Open JTalk voices can be named instead of pathed (`--ojt-voice
  mei_happy`), are looked for in
  `~/.local/share/iroha-reader-cli/hts-voice` as well as the system
  directories, and a Mei voice is preferred when the flat apt default
  is not installed. `--list-speakers --engine openjtalk` shows the
  names, and an unknown name lists what is there
  ([#9](https://github.com/hjosugi/iroha-reader-cli/issues/9)).
- Markdown headings survive extraction and become chapters: written
  into the mp3 as ID3 chapter frames (`--chapter-level`,
  `--no-chapters`), or one file per chapter with
  `--split-by-heading LEVEL`. Splitting after a normal run is free,
  since the segments are already cached
  ([#5](https://github.com/hjosugi/iroha-reader-cli/issues/5)).

- epub input, with nothing but the standard library: the spine gives
  the reading order and the `<h*>` tags give the chapters, so
  `novel.epub --split-by-heading 1` writes one audio file per chapter
  ([#8](https://github.com/hjosugi/iroha-reader-cli/issues/8)).

### Changed

- `ConvertResult.lines` is now a tuple of `Line` (text plus heading
  level); `result.texts` gives the plain strings. `convert_all()` is
  the entry point that honours splitting, `convert()` still returns
  one result for the whole document.

## [0.8.0] - 2026-08-26

First public release.

### Added

- `--jobs N`: the local engines (espeak, Open JTalk, Piper, VOICEVOX)
  now synthesize several lines at once. Default 4.
- A library API: `convert(path, ConvertOptions(), EngineSettings())`
  returns a `ConvertResult` with the audio path, the subtitle paths,
  and the timeline.
- `-q` as a short form of `--quiet`, and `-V` for `--version`.
- `--subs` accepts a comma separated list: `--subs lrc,srt`.
- A test suite (98 tests) and GitHub Actions for lint, types, tests,
  and releases.
- A real application icon, generated by `scripts/make-icon.py`.

### Changed

- The 550 line `cli.py` became one module per job under `src/`, with
  the command line as a thin layer over `pipeline.convert()`.
- Errors are `ReaderError` subclasses instead of `sys.exit` calls. A
  failing ffmpeg or a missing voice prints one clear line, names the
  install command where there is one, and exits 2. Ctrl-C exits 130.
- `--subs` on the command line now replaces the list from the config
  file instead of appending to it.
- The build scripts use `uv` and produce a smaller binary.
- Packaging moved to hatchling with a `src/` layout, and the dev
  environment is a `uv sync` away.

### Fixed

- Paths containing a single quote no longer break the ffmpeg concat
  list.
- Config file values for path options are converted to paths.
- A subtitle line that holds no words (a horizontal rule, a stray
  bullet) is dropped instead of becoming a silent segment.

## [0.7.0] - 2026-08-26

- Renamed from `reader-cli` to `iroha-reader-cli`, including the
  command, the config directory, and the Piper data directory.
- Added `scripts/build-native.sh` (single file PyInstaller binary) and
  `scripts/build-appimage.sh` (AppImage).

## [0.6.0] - 2026-08-26

- Added the Piper engine: `--engine piper`, `--piper-model`,
  `--piper-data`, `--piper-length`. `auto` prefers it for
  non-Japanese text. Piper has no official Japanese voice, so
  Japanese stays on Open JTalk or VOICEVOX.

## [0.5.0] - 2026-08-25

- Added `--dict file.tsv` to fix misreadings without touching the
  subtitles.
- Added `--list-speakers` for every engine, and `--speaker` now takes
  a VOICEVOX speaker name or `name:style`.

## [0.2.0] - 2026-08-25

- Added SRT and WebVTT output: `--subs {lrc,srt,vtt}`.

[0.11.0]: https://github.com/hjosugi/iroha-reader-cli/releases/tag/v0.11.0
[0.10.0]: https://github.com/hjosugi/iroha-reader-cli/releases/tag/v0.10.0
[0.9.0]: https://github.com/hjosugi/iroha-reader-cli/releases/tag/v0.9.0
[0.8.0]: https://github.com/hjosugi/iroha-reader-cli/releases/tag/v0.8.0
