"""iroha-reader-cli command line interface.

Turn md / pdf / txt files into one audio file plus synced subtitles.
"""

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from . import audio, extract, lrc, segment, subs, tts

DEFAULT_VOICE_JA = "ja-JP-NanamiNeural"
DEFAULT_VOICE_EN = "en-US-JennyNeural"
DEFAULT_OJT_DICT = "/var/lib/mecab/dic/open-jtalk/naist-jdic"
DEFAULT_OJT_VOICE = (
    "/usr/share/hts-voice/nitech-jp-atr503-m001/"
    "nitech_jp_atr503_m001.htsvoice"
)
OJT_VOICE_DIRS = ("/usr/share/hts-voice", "/usr/local/share/hts-voice")
DEFAULT_PIPER_MODEL = "en_US-lessac-medium"
DEFAULT_PIPER_DATA = Path.home() / ".local/share/iroha-reader-cli/piper"

_QUIET = False


def _info(msg: str) -> None:
    if not _QUIET:
        print(msg, file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="iroha-reader-cli",
        description="Convert md / pdf / txt into audio plus synced subtitles.",
    )
    p.add_argument("inputs", nargs="*", type=Path,
                   help="input files (.md .pdf .txt)")
    p.add_argument("-o", "--outdir", type=Path, default=None,
                   help="output directory (default: same as input)")
    p.add_argument("--name", default=None,
                   help="output base name (default: input file name). "
                        "Only valid with one input file")
    p.add_argument("--config", type=Path, default=None,
                   help="config file (default: ~/.config/iroha-reader-cli/config.toml)")
    p.add_argument("--engine",
                   choices=["auto", "espeak", "openjtalk", "piper", "voicevox",
                            "edge"],
                   default="auto",
                   help="tts engine (default: auto = openjtalk for Japanese, "
                        "piper for other languages, else espeak; "
                        "all free and local)")
    p.add_argument("--list-speakers", action="store_true",
                   help="list the voices/speakers of the chosen engine "
                        "and exit")
    p.add_argument("--format", choices=["mp3", "wav"], default="mp3",
                   help="output audio format (default: mp3)")
    p.add_argument("--bitrate", default="64k",
                   help="mp3 bitrate, like 128k (default: 64k)")
    p.add_argument("--loudnorm", action="store_true",
                   help="normalize loudness with the ffmpeg loudnorm filter")
    p.add_argument("--subs", action="append", choices=["lrc", "srt", "vtt"],
                   default=None,
                   help="subtitle formats to write. Repeat to add more. "
                        "Example: --subs lrc --subs srt (default: lrc)")
    p.add_argument("--gap-ms", type=int, default=200,
                   help="silence between lines in ms (default: 200)")
    p.add_argument("--max-chars", type=int, default=60,
                   help="max characters per subtitle line (default: 60)")
    p.add_argument("--pages", default=None,
                   help="pdf page range, like 3-10 or 5 or 3- (default: all)")
    p.add_argument("--dict", type=Path, default=None, dest="dict_file",
                   help="reading dictionary (TSV: word<TAB>reading). "
                        "Fixes TTS misreads. Subtitles keep the original text")
    p.add_argument("--keep-code", action="store_true",
                   help="read markdown code blocks out loud too")
    p.add_argument("--write-text", action="store_true",
                   help="also save the extracted lines as a .txt file")
    p.add_argument("--dry-run", action="store_true",
                   help="print the lines and exit, no audio")
    p.add_argument("--quiet", action="store_true",
                   help="no progress output, errors only")
    p.add_argument("--version", action="version",
                   version=f"iroha-reader-cli {__version__}")

    g = p.add_argument_group("openjtalk options (free, local, Japanese)")
    g.add_argument("--ojt-dict", default=DEFAULT_OJT_DICT,
                   help="dictionary directory")
    g.add_argument("--ojt-voice", default=DEFAULT_OJT_VOICE,
                   help=".htsvoice file. Swap it to change the voice")
    g.add_argument("--speed", type=float, default=1.0,
                   help="speech rate, 0.5 slow to 2.0 fast (default: 1.0)")
    g.add_argument("--ojt-halftone", type=float, default=0.0,
                   help="pitch shift in half tones, like 3.0 or -2.0 "
                        "(default: 0.0)")
    g.add_argument("--ojt-volume-db", type=float, default=0.0,
                   help="volume in dB, like 6.0 or -6.0 (default: 0.0)")

    g = p.add_argument_group("piper options (free, local, neural quality)")
    g.add_argument("--piper-model", default=DEFAULT_PIPER_MODEL,
                   help="voice name or .onnx path "
                        f"(default: {DEFAULT_PIPER_MODEL})")
    g.add_argument("--piper-data", type=Path, default=DEFAULT_PIPER_DATA,
                   help="directory with downloaded .onnx voices")
    g.add_argument("--piper-length", type=float, default=1.0,
                   help="length scale, bigger is slower (default: 1.0)")

    g = p.add_argument_group("espeak options (free, local, many languages)")
    g.add_argument("--lang", default=None,
                   help="voice/language, like ja or en. Variants work too, "
                        "like ja+f3 (female 3) or en+m2 (default: auto)")
    g.add_argument("--wpm", type=int, default=175,
                   help="words per minute (default: 175)")
    g.add_argument("--es-pitch", type=int, default=None,
                   help="pitch 0-99 (default: engine default 50)")
    g.add_argument("--es-amp", type=int, default=None,
                   help="amplitude 0-200 (default: engine default 100)")

    g = p.add_argument_group("voicevox options (free, local server, Japanese)")
    g.add_argument("--voicevox-url", default="http://127.0.0.1:50021",
                   help="engine url (default: http://127.0.0.1:50021)")
    g.add_argument("--speaker", default="3",
                   help="style id, speaker name, or name:style. Examples: "
                        "8 / Zundamon / Zundamon:Amaama (default: 3). "
                        "See --list-speakers")
    g.add_argument("--vv-speed", type=float, default=1.0,
                   help="speedScale (default: 1.0)")
    g.add_argument("--vv-pitch", type=float, default=0.0,
                   help="pitchScale, small values like 0.05 (default: 0.0)")
    g.add_argument("--vv-intonation", type=float, default=1.0,
                   help="intonationScale (default: 1.0)")
    g.add_argument("--vv-volume", type=float, default=1.0,
                   help="volumeScale (default: 1.0)")

    g = p.add_argument_group("edge options (no charge, online, unofficial)")
    g.add_argument("--voice", default=None,
                   help="voice name (default: auto by language)")
    g.add_argument("--rate", default="+0%",
                   help="speech rate, like +10%% (default: +0%%)")
    g.add_argument("--edge-pitch", default="+0Hz",
                   help="pitch, like +20Hz or -20Hz (default: +0Hz)")
    g.add_argument("--edge-volume", default="+0%",
                   help="volume, like +20%% or -20%% (default: +0%%)")
    g.add_argument("--concurrency", type=int, default=4,
                   help="parallel requests (default: 4)")
    return p


def _load_config(explicit: Path | None) -> dict:
    """Read the TOML config file. Return {} when there is none."""
    if explicit is not None:
        path = explicit
        if not path.is_file():
            sys.exit(f"error: config file not found: {path}")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        path = Path(xdg) / "iroha-reader-cli" / "config.toml"
        if not path.is_file():
            return {}
    try:
        import tomllib
    except ImportError:
        sys.exit("error: the config file needs Python 3.11 or newer.")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as err:
        sys.exit(f"error: bad config file {path}: {err}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    # Pass 1: find --config only.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path, default=None)
    known, _ = pre.parse_known_args(argv)

    # Pass 2: config values become defaults. CLI flags win over them.
    parser = _build_parser()
    cfg = _load_config(known.config)
    if cfg:
        valid = {a.dest for a in parser._actions}
        defaults = {}
        for key, value in cfg.items():
            dest = key.replace("-", "_")
            if dest == "dict":
                dest = "dict_file"
            if dest not in valid:
                print(f"warning: unknown config key: {key}", file=sys.stderr)
                continue
            defaults[dest] = value
        parser.set_defaults(**defaults)
    return parser.parse_args(argv)


def _parse_pages(spec: str) -> tuple[int, int | None]:
    """Parse a page range like 3-10, 5, or 3-."""
    try:
        if "-" in spec:
            a, b = spec.split("-", 1)
            start = int(a)
            end = int(b) if b else None
        else:
            start = end = int(spec)
        if start < 1 or (end is not None and end < start):
            raise ValueError
        return start, end
    except ValueError:
        sys.exit(f"error: bad page range: {spec} (use 3-10, 5, or 3-)")


def _load_dict(path: Path) -> list[tuple[str, str]]:
    """Load a TSV reading dictionary. Longest words first."""
    if not path.is_file():
        sys.exit(f"error: dictionary file not found: {path}")
    rules: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            sys.exit(f"error: bad dictionary line (need word<TAB>reading): "
                     f"{raw!r}")
        rules.append((parts[0], parts[1]))
    rules.sort(key=lambda r: len(r[0]), reverse=True)
    return rules


def _apply_dict(text: str, rules: list[tuple[str, str]]) -> str:
    for word, reading in rules:
        text = text.replace(word, reading)
    return text


def _check_tools() -> None:
    """Fail early when a needed command is missing."""
    missing = [c for c in ("ffmpeg", "ffprobe") if shutil.which(c) is None]
    if missing:
        sys.exit(f"error: missing commands: {', '.join(missing)}. "
                 "Install them first.")


def _ojt_available(args: argparse.Namespace) -> bool:
    """Return True when open_jtalk and its data files are present."""
    return (
        shutil.which("open_jtalk") is not None
        and Path(args.ojt_dict).is_dir()
        and Path(args.ojt_voice).is_file()
    )


def _resolve_piper_model(args: argparse.Namespace) -> str | None:
    """Return the .onnx path for --piper-model, or None."""
    model = Path(args.piper_model)
    if model.is_file():
        return str(model)
    candidate = Path(args.piper_data) / f"{args.piper_model}.onnx"
    if candidate.is_file():
        return str(candidate)
    return None


def _piper_available(args: argparse.Namespace) -> bool:
    """Return True when piper and the chosen voice are present."""
    return (shutil.which("piper") is not None
            and _resolve_piper_model(args) is not None)


def _resolve_speaker(args: argparse.Namespace) -> int:
    """Turn --speaker into a voicevox style id.

    Accepts a raw id, a speaker name, or name:style.
    """
    spec = str(args.speaker)
    try:
        return int(spec)
    except ValueError:
        pass
    name, _, style = spec.partition(":")
    data = tts.VoicevoxEngine.fetch_speakers(args.voicevox_url)
    for sp in data:
        if sp.get("name") != name:
            continue
        styles = sp.get("styles", [])
        if not style:
            return styles[0]["id"]
        for st in styles:
            if st.get("name") == style:
                return st["id"]
        names = ", ".join(st.get("name", "?") for st in styles)
        sys.exit(f"error: style not found: {style}. "
                 f"Styles of {name}: {names}")
    sys.exit(f"error: speaker not found: {name}. See --list-speakers")


def _list_speakers(args: argparse.Namespace) -> None:
    """Print the voices of the chosen engine."""
    engine = args.engine
    if engine == "auto":
        # Prefer a running voicevox engine. Fall back to espeak.
        try:
            data = tts.VoicevoxEngine.fetch_speakers(args.voicevox_url,
                                                     timeout=3)
            print("# voicevox styles (use the id or name with --speaker)")
            _print_vv_speakers(data)
            return
        except SystemExit:
            engine = "espeak"

    if engine == "voicevox":
        data = tts.VoicevoxEngine.fetch_speakers(args.voicevox_url)
        print("# voicevox styles (use the id or name with --speaker)")
        _print_vv_speakers(data)
    elif engine == "openjtalk":
        print("# open_jtalk voices (use the path with --ojt-voice)")
        found = False
        for root in OJT_VOICE_DIRS:
            base = Path(root)
            if not base.is_dir():
                continue
            for f in sorted(base.rglob("*.htsvoice")):
                print(f)
                found = True
        if not found:
            print("(none found. Install hts-voice-* packages or download "
                  "a .htsvoice file)")
    elif engine == "piper":
        print("# piper voices (use the name or path with --piper-model)")
        base = Path(args.piper_data)
        found = False
        if base.is_dir():
            for f in sorted(base.rglob("*.onnx")):
                print(f.stem)
                found = True
        if not found:
            print(f"(none found in {base})")
        print()
        print("# get more voices (samples: "
              "https://rhasspy.github.io/piper-samples/):")
        print(f"#   python3 -m piper.download_voices en_US-amy-medium "
              f"--download-dir {base}")
    elif engine == "edge":
        import asyncio

        import edge_tts

        voices = asyncio.run(edge_tts.list_voices())
        print("# edge voices (use the ShortName with --voice)")
        for v in voices:
            if args.lang and not v["Locale"].lower().startswith(
                    args.lang.lower()):
                continue
            print(f'{v["ShortName"]:<42} {v["Gender"]:<8} {v["Locale"]}')
    else:
        if shutil.which("espeak-ng") is None:
            sys.exit("error: espeak-ng is missing.")
        import subprocess

        cmd = ["espeak-ng", "--voices"]
        if args.lang:
            cmd = ["espeak-ng", f"--voices={args.lang}"]
        print("# espeak voices (use the language code with --lang)")
        subprocess.run(cmd, check=True)


def _print_vv_speakers(data: list) -> None:
    for sp in data:
        for st in sp.get("styles", []):
            print(f'{st.get("id", "?"):>4}  {sp.get("name", "?")} '
                  f'({st.get("name", "?")})')


def _pick_engine(args: argparse.Namespace, text: str):
    japanese = segment.has_japanese(text)

    engine = args.engine
    if engine == "auto":
        # Prefer the best free local engine for the content.
        if japanese:
            engine = "openjtalk" if _ojt_available(args) else "espeak"
        else:
            engine = "piper" if _piper_available(args) else "espeak"

    if engine == "piper":
        model = _resolve_piper_model(args)
        if shutil.which("piper") is None or model is None:
            sys.exit(
                "error: piper is not ready. Install it and get a voice:\n"
                "  pip install piper-tts\n"
                f"  mkdir -p {args.piper_data}\n"
                f"  python3 -m piper.download_voices {args.piper_model} "
                f"--download-dir {args.piper_data}"
            )
        return tts.PiperEngine(model, length_scale=args.piper_length)

    if engine == "edge":
        voice = args.voice
        if voice is None:
            voice = DEFAULT_VOICE_JA if japanese else DEFAULT_VOICE_EN
        return tts.EdgeEngine(voice, rate=args.rate, pitch=args.edge_pitch,
                              volume=args.edge_volume,
                              concurrency=args.concurrency)

    if engine == "voicevox":
        return tts.VoicevoxEngine(
            url=args.voicevox_url, speaker=_resolve_speaker(args),
            speed=args.vv_speed, pitch=args.vv_pitch,
            intonation=args.vv_intonation, volume=args.vv_volume,
        )

    if engine == "openjtalk":
        if not _ojt_available(args):
            sys.exit(
                "error: open_jtalk is not ready. Install it first:\n"
                "  sudo apt install open-jtalk open-jtalk-mecab-naist-jdic "
                "hts-voice-nitech-jp-atr503-m001"
            )
        return tts.OpenJTalkEngine(
            args.ojt_dict, args.ojt_voice, speed=args.speed,
            halftone=args.ojt_halftone, volume_db=args.ojt_volume_db,
        )

    if shutil.which("espeak-ng") is None:
        sys.exit("error: espeak-ng is missing. Install it first:\n"
                 "  sudo apt install espeak-ng")
    lang = args.lang or ("ja" if japanese else "en")
    return tts.EspeakEngine(lang=lang, wpm=args.wpm,
                            pitch=args.es_pitch, amplitude=args.es_amp)


def _process(path: Path, args: argparse.Namespace,
             dict_rules: list[tuple[str, str]] | None) -> None:
    if not path.exists():
        sys.exit(f"error: file not found: {path}")

    _info(f"* {path}")
    pages = _parse_pages(args.pages) if args.pages else None
    if pages and path.suffix.lower() != ".pdf":
        print("warning: --pages works with pdf only. Ignored.",
              file=sys.stderr)
        pages = None
    text = extract.extract(path, keep_code=args.keep_code, pages=pages)
    lines = segment.segment(text, max_chars=args.max_chars)
    if not lines:
        sys.exit(f"error: no text found in {path}")
    _info(f"  lines: {len(lines)}")

    if args.dry_run:
        for line in lines:
            print(line)
        return

    # The dictionary changes only what is spoken.
    # Subtitles keep the original text.
    spoken = ([_apply_dict(l, dict_rules) for l in lines]
              if dict_rules else lines)

    outdir = args.outdir if args.outdir is not None else path.parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = args.name or path.stem
    audio_path = outdir / f"{stem}.{args.format}"
    formats = args.subs or ["lrc"]

    engine = _pick_engine(args, text)
    _info(f"  engine: {engine.name}")

    with tempfile.TemporaryDirectory(prefix="iroha_reader_cli_") as tmp:
        seg_paths = engine.synth_all(spoken, tmp)

        # Measure each segment. Build cumulative start times.
        durations = [audio.duration_sec(p) for p in seg_paths]
        gap = args.gap_ms / 1000.0
        starts: list[float] = []
        t = 0.0
        for d in durations:
            starts.append(t)
            t += d + gap
        total = t - gap if durations else 0.0

        # Insert silence files between segments.
        concat_list = []
        if args.gap_ms > 0 and len(seg_paths) > 1:
            rate = audio.sample_rate(seg_paths[0])
            sil = f"{tmp}/silence.{engine.ext}"
            audio.make_silence(sil, args.gap_ms, rate)
            for i, p in enumerate(seg_paths):
                concat_list.append(p)
                if i < len(seg_paths) - 1:
                    concat_list.append(sil)
        else:
            concat_list = seg_paths

        audio.concat(concat_list, str(audio_path),
                     bitrate=args.bitrate, loudnorm=args.loudnorm)

    written: list[Path] = []
    if "lrc" in formats:
        p = outdir / f"{stem}.lrc"
        p.write_text(lrc.build(lines, starts, title=stem, total_sec=total),
                     encoding="utf-8", newline="\n")
        written.append(p)
    if "srt" in formats:
        p = outdir / f"{stem}.srt"
        p.write_text(subs.build_srt(lines, starts, durations),
                     encoding="utf-8", newline="\n")
        written.append(p)
    if "vtt" in formats:
        p = outdir / f"{stem}.vtt"
        p.write_text(subs.build_vtt(lines, starts, durations),
                     encoding="utf-8", newline="\n")
        written.append(p)

    if args.write_text:
        txt_path = outdir / f"{stem}.lines.txt"
        txt_path.write_text("\n".join(lines) + "\n",
                            encoding="utf-8", newline="\n")

    _info(f"  wrote: {audio_path}")
    for p in written:
        _info(f"  wrote: {p}")


def main(argv: list[str] | None = None) -> None:
    global _QUIET
    args = _parse_args(argv)
    _QUIET = args.quiet
    tts.QUIET = args.quiet

    if args.list_speakers:
        _list_speakers(args)
        return

    if not args.inputs:
        sys.exit("error: no input files. See iroha-reader-cli --help")
    if args.name and len(args.inputs) > 1:
        sys.exit("error: --name works with one input file only")

    dict_rules = _load_dict(args.dict_file) if args.dict_file else None

    if not args.dry_run:
        _check_tools()
    for path in args.inputs:
        _process(path, args, dict_rules)


if __name__ == "__main__":
    main()
