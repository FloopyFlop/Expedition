from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import ExpeditionConfig, resolve_storage_paths
from ..events import EventLogger
from ..job.state import JobState
from .interfaces import ArchiveStore, JobStateStore, SitemapStore


class _StubJobStateStore(JobStateStore):
    def load(self) -> JobState:  # pragma: no cover - stub
        raise NotImplementedError("Remote job state store is not implemented.")

    def save(self, state: JobState) -> None:  # pragma: no cover - stub
        raise NotImplementedError("Remote job state store is not implemented.")

    def read_status(self) -> str | None:  # pragma: no cover - stub
        raise NotImplementedError("Remote job state store is not implemented.")


class _StubSitemapStore(SitemapStore):
    def append(self, entry: dict[str, Any]) -> None:  # pragma: no cover - stub
        raise NotImplementedError("Remote sitemap store is not implemented.")

    def iter_entries(self, offset: int = 0, limit: int | None = None):  # pragma: no cover - stub
        raise NotImplementedError("Remote sitemap store is not implemented.")


class _StubArchiveStore(ArchiveStore):
    def write_page(self, request):  # pragma: no cover - stub
        raise NotImplementedError("Remote archive store is not implemented.")

    def read_metadata(self, page_id: str):  # pragma: no cover - stub
        raise NotImplementedError("Remote archive store is not implemented.")

    def read_request(self, page_id: str):  # pragma: no cover - stub
        raise NotImplementedError("Remote archive store is not implemented.")

    def read_response_headers(self, page_id: str):  # pragma: no cover - stub
        raise NotImplementedError("Remote archive store is not implemented.")

    def body_path(self, page_id: str):  # pragma: no cover - stub
        raise NotImplementedError("Remote archive store is not implemented.")


class RemoteBackendStub:
    def __init__(self, workspace: Path, config: ExpeditionConfig) -> None:
        self.workspace = workspace
        self.config = config
        self.paths = resolve_storage_paths(workspace, config.storage)
        self.job_state: JobStateStore = _StubJobStateStore()
        self.sitemap: SitemapStore = _StubSitemapStore()
        self.archive: ArchiveStore = _StubArchiveStore()
        self.events = EventLogger(self.paths.events_path)

    def ensure_workspace(self) -> None:  # pragma: no cover - stub
        raise NotImplementedError("Remote backend is not implemented.")
