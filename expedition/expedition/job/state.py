from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FrontierItem:
    url_original: str
    url_normalized: str
    depth: int
    parent_page_id: str | None
    page_id: str
    discovered_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "url_original": self.url_original,
            "url_normalized": self.url_normalized,
            "depth": self.depth,
            "parent_page_id": self.parent_page_id,
            "page_id": self.page_id,
            "discovered_at": self.discovered_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FrontierItem":
        return FrontierItem(
            url_original=str(data.get("url_original", "")),
            url_normalized=str(data.get("url_normalized", "")),
            depth=int(data.get("depth", 0)),
            parent_page_id=data.get("parent_page_id"),
            page_id=str(data.get("page_id", "")),
            discovered_at=str(data.get("discovered_at", "")),
        )


@dataclass
class JobState:
    job_id: str
    status: str
    created_at: str
    updated_at: str
    frontier: list[FrontierItem]
    in_flight: list[FrontierItem]
    visited_url_fingerprints: list[str]
    page_id_map: dict[str, str]
    counters: dict[str, int]
    next_page_id: int
    last_checkpoint_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "frontier": [item.to_dict() for item in self.frontier],
            "in_flight": [item.to_dict() for item in self.in_flight],
            "visited_url_fingerprints": list(self.visited_url_fingerprints),
            "page_id_map": dict(self.page_id_map),
            "counters": dict(self.counters),
            "next_page_id": int(self.next_page_id),
            "last_checkpoint_at": self.last_checkpoint_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "JobState":
        return JobState(
            job_id=str(data.get("job_id", "")),
            status=str(data.get("status", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            frontier=[
                FrontierItem.from_dict(item) for item in data.get("frontier", [])
            ],
            in_flight=[
                FrontierItem.from_dict(item) for item in data.get("in_flight", [])
            ],
            visited_url_fingerprints=list(data.get("visited_url_fingerprints", [])),
            page_id_map=dict(data.get("page_id_map", {})),
            counters=dict(data.get("counters", _default_counters())),
            next_page_id=int(data.get("next_page_id", 1)),
            last_checkpoint_at=data.get("last_checkpoint_at"),
        )


def _default_counters() -> dict[str, int]:
    return {"fetched": 0, "skipped": 0, "failed": 0, "queued": 0}
