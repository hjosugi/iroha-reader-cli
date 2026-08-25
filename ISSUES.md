# iroha-reader-cli issue backlog

Copy each section into a GitHub issue as needed.

## #1 Word-level Enhanced LRC via edge-tts WordBoundary events
labels: enhancement, priority-high

The edge service sends a WordBoundary event for each word. The event
has an offset and a duration. Use these to emit Enhanced LRC
(`<mm:ss.xx>` inside a line). Then karaoke players can highlight
word by word, not line by line.

Plan:
- Use `Communicate.stream()` per line. Collect audio and events.
- Map event offsets to the global timeline (add the line start time).
- Add `--lrc-style {line,word}`.

## #2 Add a GUI
labels: enhancement

The CLI covers the main flow. Add a small GUI for drag and drop use.
Candidates:
- Local web UI (FastAPI + one HTML page)
- Tauri wrapper around the same Python core

Decide after #1. Keep the core as a library so both can call it.

## #3 Offline high-quality engine: piper (DONE in v0.6.0)
labels: enhancement, done

Done: `--engine piper` with `--piper-model`, `--piper-data`, and
`--piper-length`. auto prefers piper for non-Japanese text. Checked:
there is no official Japanese piper voice, so Japanese stays on
openjtalk / voicevox.

## #4 Better PDF extraction for multi-column layouts
labels: enhancement

pypdf reads some PDFs in the wrong order. Options:
- Shell out to `pdftotext -layout` when available.
- Or use pdfplumber and sort by position.
Add `--pdf-backend {pypdf,pdftotext}`.

## #5 Segment cache for re-runs
labels: enhancement

Synthesis is the slow part. Cache each segment by a hash of
(engine, voice, rate, text). On a re-run, only changed lines are
synthesized again. Store under `~/.cache/iroha-reader-cli/`.

## #6 Chapter markers from markdown headings
labels: enhancement

Keep heading info during extraction. Then:
- Add chapter comment lines to the LRC.
- Optional `--split-by-heading` to write one audio + LRC per chapter.

## #7 Export SRT and VTT too (DONE in v0.2.0)
labels: enhancement, done

The start times are already known. End times are start + duration.
Done: `--subs {lrc,srt,vtt}` (repeatable) is implemented.
SRT/VTT open the video subtitle use case.

## #8 Handle edge service throttling better
labels: bug, robustness

Retries are per line only. Add:
- A global backoff when many lines fail in a row.
- `--min-interval-ms` to slow down requests.
- A clear error message that names the throttling cause.

## #9 Tests and CI
labels: chore

- Unit tests for extract, segment, and lrc (pure functions, no network).
- A smoke test with espeak-ng in GitHub Actions (ubuntu-latest).
- ruff + mypy.

## #10 Publish to PyPI
labels: chore

- Reserve the package name.
- Build with `python -m build`. Publish via trusted publishing.
- Document `pipx install iroha-reader-cli`.

## #11 epub input support
labels: enhancement

epub is zipped html. Parse chapters with `ebooklib` or plain
`zipfile` + html stripping. This makes iroha-reader-cli a book-to-audiobook
tool with synced text.

## #12 Japanese reading corrections (DONE in v0.5.0)
labels: enhancement, done

Done: `--dict file.tsv` (word<TAB>reading). Replacements apply to
the spoken audio only. Subtitles keep the original text.

## #13 Nicer Open JTalk voice (Mei)
labels: enhancement

The apt voice (nitech m001) sounds flat. The MMDAgent "Mei" voice is
free and sounds better. It is not in apt. Add:
- A short doc section on where to download Mei.
- Auto-detect common install paths for `--ojt-voice`.

## #14 VOICEVOX speaker list helper (DONE in v0.5.0)
labels: enhancement, done

Done: `--list-speakers` covers all four engines. `--speaker` also
takes a name or name:style and resolves it via `GET /speakers`.

## #15 Named profiles in the config file
labels: enhancement

One config file, many presets. Example:

    [profile.study]
    engine = "voicevox"
    vv-speed = 1.3

    [profile.relax]
    engine = "openjtalk"
    speed = 0.9

Use with `iroha-reader-cli notes.md --profile study`.

## #16 More native build targets
labels: enhancement

x86-64 Linux is covered: `scripts/build-native.sh` (PyInstaller
one-file) and `scripts/build-appimage.sh` (AppImage) since v0.7.0.
Still open:
- arm64 Linux (build on an arm64 host or qemu).
- A Nuitka variant for faster start time and a smaller file.
- CI release workflow that attaches the binary and the AppImage to
  GitHub releases.
- A real icon for the AppImage.

## #17 Read from stdin
labels: enhancement

Support `-` as the input: `cat notes.md | iroha-reader-cli - --type md`.
Needs a `--type` flag because there is no file suffix.
