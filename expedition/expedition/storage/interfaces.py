from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Protocol

from ..events import EventLogger
from ..job.state import JobState
from ..config import StoragePaths
from .models import ArchiveWriteRequest, ArchiveWriteResult


class JobStateStore(ABC):
    @abstractmethod
    def load(self) -> JobState:
        raise NotImplementedError

    @abstractmethod
    def save(self, state: JobState) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_status(self) -> str | None:
        raise NotImplementedError


class SitemapStore(ABC):
    @abstractmethod
    def append(self, entry: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def iter_entries(self, offset: int = 0, limit: int | None = None) -> Iterable[dict[str, Any]]:
        raise NotImplementedError


class ArchiveStore(ABC):
    @abstractmethod
    def write_page(self, request: ArchiveWriteRequest) -> ArchiveWriteResult:
        raise NotImplementedError

    @abstractmethod
    def read_metadata(self, page_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def read_request(self, page_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def read_response_headers(self, page_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def body_path(self, page_id: str) -> Path | None:
        raise NotImplementedError


class StorageBackend(Protocol):
    paths: StoragePaths
    job_state: JobStateStore
    sitemap: SitemapStore
    archive: ArchiveStore
    events: EventLogger

    def ensure_workspace(self) -> None:
        raise NotImplementedError
