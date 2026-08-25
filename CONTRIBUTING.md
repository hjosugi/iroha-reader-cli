# Contributing

Bug reports and pull requests are welcome.

## Setup

The project uses [uv](https://docs.astral.sh/uv/). One command gets
you a virtual environment with everything pinned by `uv.lock`:

```sh
uv sync
```

The tool itself needs `ffmpeg`, and at least one engine. espeak-ng is
the smallest one to install and the one the tests use:

```sh
sudo apt install ffmpeg espeak-ng
```

## Checks

```sh
uv run pytest             # tests
uv run pytest -m "not slow"   # skip the ones that need ffmpeg + espeak-ng
uv run ruff check .       # lint
uv run mypy               # types (strict)
```

All three run in CI on Python 3.11, 3.12, and 3.13. Please keep them
green.

## Layout

```
src/iroha_reader_cli/
  cli.py         flags in, exit code out. No logic beyond that
  pipeline.py    the conversion: extract, segment, synthesize, join, write
  extract.py     md / pdf / txt -> plain text
  segment.py     text -> short lines
  timeline.py    measured lengths -> start times
  subtitles.py   lines + timeline -> lrc / srt / vtt
  audio.py       ffmpeg and ffprobe
  engines/       one module per TTS engine, behind engines/base.py
  errors.py      ReaderError and friends
```

Two rules keep it that way:

- The core raises `ReaderError`; only `cli.py` prints and exits.
- Everything that can be tested without audio hardware lives in a pure
  function. Add a unit test for it.

## Adding an engine

1. Add `engines/yours.py` with a class deriving from `LocalEngine`
   (one subprocess or request per line) or `Engine` (anything else).
2. Register it in `engines/__init__.py`: the name in `ENGINE_NAMES`,
   its settings fields in `EngineSettings`, and a branch in `create()`.
3. Add the flags to `cli.py` and a row to the README tables.
4. Add a case to `tests/test_engines.py`.

## Commits

Short summary line in the imperative, a blank line, then why the
change was needed. Reference issues as #3.
