"""A small local web UI.

The page calls itself iroha-reader: there is no command line on it.

`iroha-reader-cli --serve` opens one page in the browser: drop a
document on it, get the audio back with the text highlighting itself
line by line. It is the shortest way to see what the timing is for.

The server is the standard library only, binds to localhost, and holds
its files in a temporary directory that goes away when it stops.
"""

from __future__ import annotations

import json
import secrets
import shutil
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import engines, extract
from .engines import EngineSettings
from .errors import ReaderError
from .pipeline import ConvertOptions, ConvertResult, convert
from .reporting import Reporter

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
#: Bigger than any document worth reading out loud.
MAX_UPLOAD = 32 * 1024 * 1024

MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".lrc": "text/plain; charset=utf-8",
    ".srt": "text/plain; charset=utf-8",
    ".vtt": "text/vtt; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


@dataclass(frozen=True, slots=True)
class Job:
    """One finished conversion, kept until the server stops."""

    id: str
    directory: Path
    result: ConvertResult

    def payload(self) -> dict[str, Any]:
        """The conversion as the page wants it: paths become urls."""
        payload = self.result.as_dict()
        payload.update({
            "id": self.id,
            "audio": f"/files/{self.id}/{self.result.audio.name}",
            "files": [f"/files/{self.id}/{path.name}"
                      for path in (self.result.audio, *self.result.subtitle_files)],
        })
        for gone in ("source", "subtitles", "text_file"):
            payload.pop(gone, None)
        return payload


class Reader:
    """Holds the options and the finished jobs."""

    def __init__(self, options: ConvertOptions, settings: EngineSettings,
                 reporter: Reporter, root: Path):
        self.options = options
        self.settings = settings
        self.reporter = reporter
        self.root = root
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def convert(self, data: bytes, name: str, kind: str, engine: str,
                word_timing: bool) -> Job:
        """Convert one uploaded document."""
        if not data.strip():
            raise ReaderError("that file is empty")
        if kind not in extract.INPUT_TYPES:
            raise ReaderError(f"unknown document type: {kind}")
        if engine not in engines.ENGINE_NAMES:
            raise ReaderError(f"unknown engine: {engine}")

        job_id = secrets.token_hex(8)
        directory = self.root / job_id
        directory.mkdir(parents=True)
        stem = Path(name).stem or "document"
        source = directory / f"input.{kind}"
        source.write_bytes(data)

        options = _replace(self.options, outdir=directory, name=stem,
                           source_label=name)
        settings = _replace(self.settings, requested=engine,
                            word_timing=word_timing)
        result = convert(source, options, settings, self.reporter)

        job = Job(job_id, directory, result)
        with self._lock:
            self.jobs[job_id] = job
        return job

    def file(self, job_id: str, name: str) -> Path | None:
        """Look up one output file. Only names this server wrote are served."""
        with self._lock:
            job = self.jobs.get(job_id)
        if job is None:
            return None
        allowed = {path.name: path for path in
                   (job.result.audio, *job.result.subtitle_files)}
        return allowed.get(name)


def _replace(source: Any, **changes: Any) -> Any:
    """A shallow copy with fields replaced (the dataclasses use slots)."""
    import dataclasses

    return dataclasses.replace(source, **changes)


class _Handler(BaseHTTPRequestHandler):
    server_version = "iroha-reader"
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> Reader:
        app: Reader = self.server.app  # type: ignore[attr-defined]
        return app

    def log_message(self, _fmt: str, *_args: Any) -> None:
        # The Reporter owns the output; the default logger is noise.
        return

    def do_GET(self) -> None:
        route = urlparse(self.path)
        if route.path in ("/", "/index.html"):
            self._send_bytes(page().encode("utf-8"), MEDIA_TYPES[".html"])
            return
        if route.path.startswith("/files/"):
            parts = route.path.split("/")
            if len(parts) == 4:
                path = self.app.file(parts[2], parts[3])
                if path is not None and path.is_file():
                    self._send_file(path)
                    return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route = urlparse(self.path)
        if route.path != "/api/convert":
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._send_json({"error": "nothing to convert"}, HTTPStatus.BAD_REQUEST)
            return
        if length > MAX_UPLOAD:
            self._send_json({"error": "that file is too big"},
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return

        query = parse_qs(route.query)
        data = self.rfile.read(length)
        try:
            job = self.app.convert(
                data,
                name=_one(query, "name", "document"),
                kind=_one(query, "type", "md"),
                engine=_one(query, "engine", "auto"),
                word_timing=_one(query, "words", "0") == "1",
            )
        except ReaderError as err:
            self._send_json({"error": str(err)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json(job.payload())

    def _send_file(self, path: Path) -> None:
        """Serve a file, honouring Range so the audio element can seek."""
        media = MEDIA_TYPES.get(path.suffix, "application/octet-stream")
        data = path.read_bytes()
        span = _parse_range(self.headers.get("Range"), len(data))
        if span is None:
            self._send_bytes(data, media, extra={"Accept-Ranges": "bytes"})
            return
        start, end = span
        self._send_bytes(
            data[start:end + 1], media, HTTPStatus.PARTIAL_CONTENT,
            extra={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{len(data)}",
            },
        )

    def _send_json(self, payload: dict[str, Any],
                   status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_bytes(self, body: bytes, media: str,
                    status: HTTPStatus = HTTPStatus.OK,
                    extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(body)))
        # Everything here is local and per session; never let it be cached.
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Parse one `bytes=start-end` range. Anything odd means "send it all"."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    first, _, last = header[len("bytes="):].partition("-")
    try:
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        elif last:
            # A suffix range: the last N bytes.
            start = max(0, size - int(last))
            end = size - 1
        else:
            return None
    except ValueError:
        return None
    if start >= size or start < 0 or end < start:
        return None
    return start, min(end, size - 1)


def _one(query: dict[str, list[str]], key: str, fallback: str) -> str:
    values = query.get(key) or []
    return values[0] if values and values[0] else fallback


def page() -> str:
    """The single page of the UI."""
    return (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")


def make_server(app: Reader, host: str = DEFAULT_HOST,
                port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Bind the server. Port 0 picks a free one, which the tests use."""
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.app = app  # type: ignore[attr-defined]
    return server


def serve(options: ConvertOptions, settings: EngineSettings, reporter: Reporter,
          host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          open_browser: bool = True) -> None:
    """Run the web UI until Ctrl-C."""
    with tempfile.TemporaryDirectory(prefix="iroha_serve_") as tmp:
        server = make_server(Reader(options, settings, reporter, Path(tmp)), host, port)
        url = f"http://{host}:{server.server_address[1]}/"
        reporter.info(f"reading room: {url}")
        if host not in ("127.0.0.1", "localhost", "::1"):
            reporter.warn(f"listening on {host}, which is not just this machine")
        reporter.info("stop with Ctrl-C")
        if open_browser:
            threading.Timer(0.5, webbrowser.open, args=(url,)).start()
        try:
            server.serve_forever()
        finally:
            server.server_close()
            shutil.rmtree(tmp, ignore_errors=True)
