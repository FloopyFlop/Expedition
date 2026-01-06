from __future__ import annotations

import contextlib
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return


@contextlib.contextmanager
def _serve_directory(path: Path) -> Iterator[str]:
    handler = partial(QuietHandler, directory=str(path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def local_site(tmp_path: Path) -> Iterator[str]:
    site_dir = tmp_path / "site"
    site_dir.mkdir()

    (site_dir / "index.html").write_text(
        """
        <html><head><title>Index</title></head>
        <body>
          <a href=\"/a.html\">A</a>
          <a href=\"/b.html\">B</a>
        </body></html>
        """,
        encoding="utf-8",
    )
    (site_dir / "a.html").write_text(
        """
        <html><head><title>A</title></head>
        <body>
          <a href=\"/a1.html\">A1</a>
        </body></html>
        """,
        encoding="utf-8",
    )
    (site_dir / "b.html").write_text(
        """
        <html><head><title>B</title></head>
        <body>
          <a href=\"/b1.html\">B1</a>
        </body></html>
        """,
        encoding="utf-8",
    )
    (site_dir / "a1.html").write_text(
        "<html><head><title>A1</title></head><body>A1</body></html>",
        encoding="utf-8",
    )
    (site_dir / "b1.html").write_text(
        "<html><head><title>B1</title></head><body>B1</body></html>",
        encoding="utf-8",
    )

    with _serve_directory(site_dir) as base_url:
        yield base_url
