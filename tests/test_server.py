"""The local web UI."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from conftest import requires_espeak, requires_ffmpeg
from iroha_reader_cli.engines import EngineSettings
from iroha_reader_cli.errors import ReaderError
from iroha_reader_cli.pipeline import ConvertOptions
from iroha_reader_cli.reporting import Reporter
from iroha_reader_cli.server import Reader, _parse_range, make_server


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-99", (0, 99)),
        ("bytes=0-", (0, 999)),
        ("bytes=500-1500", (500, 999)),
        ("bytes=-100", (900, 999)),
        (None, None),
        ("", None),
        ("items=0-10", None),
        ("bytes=0-10,20-30", None),
        ("bytes=abc-def", None),
        ("bytes=2000-", None),
        ("bytes=500-100", None),
    ],
)
def test_range_headers(header: str | None, expected: tuple[int, int] | None) -> None:
    assert _parse_range(header, 1000) == expected


def reader(tmp_path: Path) -> Reader:
    return Reader(ConvertOptions(), EngineSettings(requested="espeak"),
                  Reporter(quiet=True), tmp_path)


def test_an_empty_upload_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="empty"):
        reader(tmp_path).convert(b"   \n", "a.md", "md", "espeak", False)


def test_an_unknown_type_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="unknown document type"):
        reader(tmp_path).convert(b"text", "a.zip", "zip", "espeak", False)


def test_an_unknown_engine_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReaderError, match="unknown engine"):
        reader(tmp_path).convert(b"text", "a.md", "md", "sing-it-yourself", False)


def test_only_files_this_server_wrote_are_served(tmp_path: Path) -> None:
    app = reader(tmp_path)
    assert app.file("nope", "a.mp3") is None


@pytest.fixture
def running(tmp_path: Path) -> Iterator[str]:
    app = Reader(ConvertOptions(), EngineSettings(requested="espeak"),
                 Reporter(quiet=True), tmp_path)
    httpd = make_server(app, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get(url: str) -> tuple[int, bytes, dict[str, str]]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read(), dict(err.headers)


def post(url: str, body: bytes) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload: dict[str, object] = json.loads(response.read())
            return response.status, payload
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_the_page_is_served(running: str) -> None:
    status, body, headers = get(running + "/")
    assert status == 200
    assert b"<title>iroha-reader-cli</title>" in body
    assert headers["Content-Type"].startswith("text/html")


def test_unknown_routes_are_json_404s(running: str) -> None:
    status, body, _ = get(running + "/nope")
    assert status == 404
    assert json.loads(body) == {"error": "not found"}


def test_a_made_up_job_id_is_a_404(running: str) -> None:
    assert get(running + "/files/deadbeef/x.mp3")[0] == 404


def test_an_empty_post_is_a_400(running: str) -> None:
    status, payload = post(running + "/api/convert?type=md", b"")
    assert status == 400
    assert "nothing" in str(payload["error"])


def test_a_bad_type_is_a_400(running: str) -> None:
    status, payload = post(running + "/api/convert?type=zip", b"hello")
    assert status == 400
    assert "unknown document type" in str(payload["error"])


@pytest.mark.slow
@requires_ffmpeg
@requires_espeak
def test_a_document_comes_back_timed_and_playable(running: str) -> None:
    document = "# Opening\n\nFirst line here.\n\n## Chapter One\n\nSecond line here.\n"
    status, payload = post(
        running + "/api/convert?name=story.md&type=md&engine=espeak",
        document.encode("utf-8"),
    )
    assert status == 200
    lines = payload["lines"]
    assert isinstance(lines, list)
    assert [line["text"] for line in lines] == [
        "Opening", "First line here.", "Chapter One", "Second line here.",
    ]
    assert lines[0]["heading"] == 1
    assert lines[0]["start"] == 0.0
    assert lines[1]["start"] > 0
    assert payload["chapters"]

    audio_url = running + str(payload["audio"])
    status, body, headers = get(audio_url)
    assert status == 200
    assert headers["Content-Type"] == "audio/mpeg"
    assert headers["Accept-Ranges"] == "bytes"
    assert len(body) > 0

    # The audio element seeks with Range requests.
    request = urllib.request.Request(audio_url, headers={"Range": "bytes=0-99"})
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 206
        assert len(response.read()) == 100
        assert response.headers["Content-Range"].endswith(f"/{len(body)}")
