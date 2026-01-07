from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ContentSummary:
    title: str | None
    h1: str | None
    word_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "h1": self.h1,
            "word_count": self.word_count,
        }


@dataclass
class ArchiveWriteRequest:
    page_id: str
    url_original: str
    url_normalized: str
    fetched_at: str
    request_headers: dict[str, str]
    response_status: int | None
    response_headers: dict[str, str]
    body: bytes
    content_type: str | None
    content_hash: str | None
    proxy_used: str | None
    text: str | None
    summary: ContentSummary | None
    annotations: dict[str, Any] | None = None


@dataclass
class ArchiveWriteResult:
    body_path: Path
    request_path: Path
    response_headers_path: Path
    metadata_path: Path
    text_path: Path | None
