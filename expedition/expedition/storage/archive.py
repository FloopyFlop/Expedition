from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import ArchiveWriteRequest, ArchiveWriteResult


class LocalArchiveStore:
    def __init__(self, archive_dir: Path) -> None:
        self.archive_dir = archive_dir
        self.pages_dir = archive_dir / "pages"

    def write_page(self, request: ArchiveWriteRequest) -> ArchiveWriteResult:
        page_dir = self.pages_dir / request.page_id
        page_dir.mkdir(parents=True, exist_ok=True)

        body_filename = _body_filename(request.content_type)
        body_path = page_dir / body_filename
        with body_path.open("wb") as handle:
            handle.write(request.body)

        request_path = page_dir / "request.json"
        response_headers_path = page_dir / "response_headers.json"
        metadata_path = page_dir / "metadata.json"

        request_payload = {
            "method": "GET",
            "url": request.url_normalized,
            "headers": request.request_headers,
            "proxy_used": _redact_proxy(request.proxy_used),
        }
        _write_json(request_path, request_payload)

        response_payload = {
            "status": request.response_status,
            "headers": request.response_headers,
        }
        _write_json(response_headers_path, response_payload)

        text_path = None
        if request.text is not None:
            text_path = page_dir / "text.txt"
            with text_path.open("w", encoding="utf-8") as handle:
                handle.write(request.text)
                handle.write("\n")

        summary_payload = request.summary.to_dict() if request.summary else None
        metadata_payload = {
            "page_id": request.page_id,
            "source_id": request.source_id,
            "url_original": request.url_original,
            "url_normalized": request.url_normalized,
            "fetched_at": request.fetched_at,
            "content_type": request.content_type,
            "content_hash": request.content_hash,
            "summary": summary_payload,
            "annotations": request.annotations,
            "storage": {
                "body": body_filename,
                "request": "request.json",
                "response_headers": "response_headers.json",
                "metadata": "metadata.json",
                "text": "text.txt" if request.text is not None else None,
            },
        }
        _write_json(metadata_path, metadata_payload)

        return ArchiveWriteResult(
            body_path=body_path,
            request_path=request_path,
            response_headers_path=response_headers_path,
            metadata_path=metadata_path,
            text_path=text_path,
        )

    def read_metadata(self, page_id: str) -> dict[str, Any] | None:
        path = self.pages_dir / page_id / "metadata.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def read_request(self, page_id: str) -> dict[str, Any] | None:
        path = self.pages_dir / page_id / "request.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def read_response_headers(self, page_id: str) -> dict[str, Any] | None:
        path = self.pages_dir / page_id / "response_headers.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def body_path(self, page_id: str) -> Path | None:
        metadata = self.read_metadata(page_id)
        if not metadata:
            return None
        storage = metadata.get("storage", {})
        body_file = storage.get("body")
        if not body_file:
            return None
        return self.pages_dir / page_id / body_file


def _body_filename(content_type: str | None) -> str:
    if content_type:
        lower_type = content_type.lower()
        if lower_type.startswith("text/") or "html" in lower_type:
            return "response_body.html"
    return "response_body.bin"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _redact_proxy(proxy_url: str | None) -> str | None:
    if not proxy_url:
        return None
    split = urlsplit(proxy_url)
    if not split.username and not split.password:
        return proxy_url
    netloc = split.hostname or ""
    if split.port:
        netloc = f"{netloc}:{split.port}"
    return urlunsplit((split.scheme, netloc, split.path, split.query, split.fragment))
