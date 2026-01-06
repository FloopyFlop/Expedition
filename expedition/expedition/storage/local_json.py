from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import ExpeditionConfig, StoragePaths, atomic_write_json, resolve_storage_paths
from ..events import EventLogger
from ..job.state import JobState
from .archive import LocalArchiveStore
from .interfaces import ArchiveStore, JobStateStore, SitemapStore


class LocalJobStateStore(JobStateStore):
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> JobState:
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return JobState.from_dict(data)

    def save(self, state: JobState) -> None:
        atomic_write_json(self.path, state.to_dict())

    def read_status(self) -> str | None:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("status")


class LocalSitemapStore(SitemapStore):
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True))
            handle.write("\n")

    def iter_entries(self, offset: int = 0, limit: int | None = None) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return []
        items: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < offset:
                    continue
                if limit is not None and len(items) >= limit:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                items.append(json.loads(stripped))
        return items


class LocalJsonBackend:
    def __init__(self, workspace: Path, config: ExpeditionConfig) -> None:
        self.workspace = workspace
        self.config = config
        self.paths: StoragePaths = resolve_storage_paths(workspace, config.storage)
        self.job_state: JobStateStore = LocalJobStateStore(self.paths.job_state_path)
        self.sitemap: SitemapStore = LocalSitemapStore(self.paths.sitemap_path)
        self.archive: ArchiveStore = LocalArchiveStore(self.paths.archive_dir)
        self.events = EventLogger(self.paths.events_path)

    def ensure_workspace(self) -> None:
        self.paths.archive_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.archive_dir / "pages").mkdir(parents=True, exist_ok=True)
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        if not self.paths.sitemap_path.exists():
            self.paths.sitemap_path.parent.mkdir(parents=True, exist_ok=True)
            self.paths.sitemap_path.touch()
        if not self.paths.events_path.exists():
            self.paths.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.paths.events_path.touch()


LocalJsonStorage = LocalJsonBackend
