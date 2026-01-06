from __future__ import annotations

import base64
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Response

from ..config import ExpeditionConfig, ParsingConfig, RenderingConfig, RequestConfig, load_config
from ..dedupe import content_hash, url_fingerprint
from ..frontier import Frontier
from ..normalize import normalize_url
from ..storage.factory import create_backend
from ..storage.interfaces import StorageBackend
from ..storage.models import ArchiveWriteRequest, ContentSummary
from .protocol import (
    ParsingPayload,
    RenderingPayload,
    RegisterWorkerResponse,
    RequestPayload,
    TaskResponse,
    TaskResult,
)
from ..job.state import FrontierItem

logger = logging.getLogger(__name__)


class MasterCoordinator:
    def __init__(self, workspace: Path, config: ExpeditionConfig, backend: StorageBackend) -> None:
        self.workspace = workspace
        self.config = config
        self.backend = backend
        self.job_state = backend.job_state.load()

        items = self.job_state.frontier + self.job_state.in_flight
        self.frontier = Frontier(config.traversal, items)
        self.job_state.in_flight = []
        self.visited = set(self.job_state.visited_url_fingerprints)
        self.page_id_map = dict(self.job_state.page_id_map)
        self.allow_patterns = [re.compile(p) for p in config.allow_patterns]
        self.deny_patterns = [re.compile(p) for p in config.deny_patterns]
        self.in_flight: dict[str, FrontierItem] = {}
        self.workers: dict[str, str] = {}
        self._lock = threading.Lock()

        self._seed_frontier_if_needed()
        self._checkpoint("master_init")

    def register_worker(self) -> str:
        worker_id = f"worker-{uuid.uuid4()}"
        with self._lock:
            self.workers[worker_id] = _utc_now()
        self.backend.events.log("worker_registered", {"worker_id": worker_id})
        return worker_id

    def next_task(self, worker_id: str) -> TaskResponse | None:
        with self._lock:
            self.workers[worker_id] = _utc_now()

            external_status = self.backend.job_state.read_status()
            if external_status:
                self.job_state.status = external_status
            if self.job_state.status in {"paused", "canceled", "completed"}:
                return None
            if self._max_pages_reached():
                if not self.in_flight:
                    self.job_state.status = "completed"
                    self._checkpoint("limit_reached")
                return None
            if self.frontier.is_empty():
                if not self.in_flight:
                    self.job_state.status = "completed"
                    self._checkpoint("frontier_empty")
                return None

            item = self.frontier.pop()
            task_id = f"task-{uuid.uuid4()}"
            self.in_flight[task_id] = item
            self._checkpoint("task_assigned")

            return TaskResponse(
                task_id=task_id,
                page_id=item.page_id,
                url_original=item.url_original,
                url_normalized=item.url_normalized,
                depth=item.depth,
                parent_page_id=item.parent_page_id,
                discovered_at=item.discovered_at,
                request=_request_payload(self.config.request),
                parsing=_parsing_payload(self.config.parsing),
                rendering=_rendering_payload(self.config.rendering),
            )

    def handle_result(self, result: TaskResult) -> None:
        with self._lock:
            item = self.in_flight.pop(result.task_id, None)
            if not item:
                raise ValueError("Unknown task_id")

            now = _utc_now()

            if result.error:
                self.job_state.counters["failed"] = (
                    self.job_state.counters.get("failed", 0) + 1
                )
                self._append_sitemap_entry(
                    item=item,
                    fetched_at=now,
                    http_status=None,
                    content_type=None,
                    content_length=None,
                    sha256=None,
                    title=None,
                    outlinks=None,
                )
                self.backend.events.log(
                    "page_failed",
                    {
                        "page_id": item.page_id,
                        "url_normalized": item.url_normalized,
                        "error": result.error,
                    },
                )
                self._checkpoint("task_failed")
                return

            body = base64.b64decode(result.body_b64) if result.body_b64 else b""
            sha = result.sha256 or (content_hash(body) if body else None)
            content_length = result.content_length if result.content_length is not None else len(body)
            content_type = result.content_type

            summary = None
            if result.title or result.h1 or result.word_count is not None:
                summary = ContentSummary(
                    title=result.title, h1=result.h1, word_count=result.word_count
                )

            self.backend.archive.write_page(
                ArchiveWriteRequest(
                    page_id=item.page_id,
                    url_original=item.url_original,
                    url_normalized=item.url_normalized,
                    fetched_at=now,
                    request_headers=self._request_headers(),
                    response_status=result.status_code,
                    response_headers=result.headers,
                    body=body,
                    content_type=content_type,
                    content_hash=sha,
                    proxy_used=result.proxy_used,
                    text=result.text,
                    summary=summary,
                )
            )

            outlinks: list[str] | None = None
            if self.config.mode == "crawl" and result.outlinks:
                normalized_links = self._normalize_and_filter_links(
                    result.outlinks, result.final_url or item.url_normalized
                )
                outlinks = [normalized for _, normalized in normalized_links]
                self._enqueue_links(normalized_links, parent=item)

            self._append_sitemap_entry(
                item=item,
                fetched_at=now,
                http_status=result.status_code,
                content_type=content_type,
                content_length=content_length,
                sha256=sha,
                title=result.title,
                outlinks=outlinks,
            )

            self.job_state.counters["fetched"] = (
                self.job_state.counters.get("fetched", 0) + 1
            )
            self.backend.events.log(
                "page_fetched",
                {
                    "page_id": item.page_id,
                    "url_normalized": item.url_normalized,
                    "status_code": result.status_code,
                    "content_type": content_type,
                },
            )
            if self._max_pages_reached() and not self.in_flight:
                self.job_state.status = "completed"
            self._checkpoint("task_completed")

    def _request_headers(self) -> dict[str, str]:
        headers = dict(self.config.request.headers)
        if self.config.request.user_agent:
            headers["User-Agent"] = self.config.request.user_agent
        return headers

    def _enqueue_links(self, links: Iterable[tuple[str, str]], parent: FrontierItem) -> None:
        if self.config.max_depth is not None and parent.depth >= self.config.max_depth:
            return

        for original, normalized in links:
            fingerprint = url_fingerprint(normalized)
            if fingerprint in self.visited:
                self.job_state.counters["skipped"] = (
                    self.job_state.counters.get("skipped", 0) + 1
                )
                continue
            page_id = self._get_or_create_page_id(normalized)
            item = FrontierItem(
                url_original=original,
                url_normalized=normalized,
                depth=parent.depth + 1,
                parent_page_id=parent.page_id,
                page_id=page_id,
                discovered_at=_utc_now(),
            )
            self.visited.add(fingerprint)
            self.frontier.push(item)

    def _normalize_and_filter_links(
        self, links: Iterable[str], base_url: str
    ) -> list[tuple[str, str]]:
        normalized_links: list[tuple[str, str]] = []
        for link in links:
            normalized = normalize_url(
                link,
                base_url=base_url,
                drop_query_param_prefixes=self.config.normalize.drop_query_param_prefixes,
            )
            if not normalized:
                continue
            if not self._in_scope(normalized):
                continue
            normalized_links.append((link, normalized))
        return normalized_links

    def _in_scope(self, url: str) -> bool:
        split = urlsplit(url)
        if split.scheme not in {"http", "https"}:
            return False
        host = split.hostname or ""
        if self.config.allowed_domains:
            allowed = False
            for domain in self.config.allowed_domains:
                domain = domain.lower()
                if host == domain or host.endswith(f".{domain}"):
                    allowed = True
                    break
            if not allowed:
                return False

        if self.deny_patterns and any(p.search(url) for p in self.deny_patterns):
            return False

        if self.allow_patterns and not any(p.search(url) for p in self.allow_patterns):
            return False

        return True

    def _seed_frontier_if_needed(self) -> None:
        if self.frontier.to_list() or self.visited:
            return

        if self.config.mode == "crawl":
            if not self.config.seed_url:
                raise ValueError("seed_url is required for crawl mode")
            normalized = normalize_url(
                self.config.seed_url,
                drop_query_param_prefixes=self.config.normalize.drop_query_param_prefixes,
            )
            page_id = self._get_or_create_page_id(normalized)
            item = FrontierItem(
                url_original=self.config.seed_url,
                url_normalized=normalized,
                depth=0,
                parent_page_id=None,
                page_id=page_id,
                discovered_at=_utc_now(),
            )
            self.frontier.push(item)
            self.visited.add(url_fingerprint(normalized))
            return

        if self.config.mode == "list":
            urls = self._read_input_urls()
            for url in urls:
                normalized = normalize_url(
                    url,
                    drop_query_param_prefixes=self.config.normalize.drop_query_param_prefixes,
                )
                if not normalized:
                    continue
                if not self._in_scope(normalized):
                    continue
                fingerprint = url_fingerprint(normalized)
                if fingerprint in self.visited:
                    continue
                page_id = self._get_or_create_page_id(normalized)
                item = FrontierItem(
                    url_original=url,
                    url_normalized=normalized,
                    depth=0,
                    parent_page_id=None,
                    page_id=page_id,
                    discovered_at=_utc_now(),
                )
                self.visited.add(fingerprint)
                self.frontier.push(item)
            return

        raise ValueError(f"Unknown mode: {self.config.mode}")

    def _read_input_urls(self) -> list[str]:
        if not self.config.input_urls_file:
            raise ValueError("input_urls_file is required for list mode")
        path = Path(self.config.input_urls_file)
        if not path.is_absolute():
            path = self.workspace / path
        if not path.exists():
            raise FileNotFoundError(str(path))
        urls = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                urls.append(stripped)
        return urls

    def _get_or_create_page_id(self, normalized_url: str) -> str:
        existing = self.page_id_map.get(normalized_url)
        if existing:
            return existing
        page_id = f"{self.job_state.next_page_id:08d}"
        self.job_state.next_page_id += 1
        self.page_id_map[normalized_url] = page_id
        return page_id

    def _append_sitemap_entry(
        self,
        *,
        item: FrontierItem,
        fetched_at: str,
        http_status: int | None,
        content_type: str | None,
        content_length: int | None,
        sha256: str | None,
        title: str | None,
        outlinks: list[str] | None,
    ) -> None:
        entry = {
            "page_id": item.page_id,
            "url_original": item.url_original,
            "url_normalized": item.url_normalized,
            "parent_page_id": item.parent_page_id,
            "depth": item.depth,
            "discovered_at": item.discovered_at,
            "fetched_at": fetched_at,
            "http_status": http_status,
            "content_type": content_type,
            "content_length": content_length,
            "sha256": sha256,
            "title": title,
            "outlinks": outlinks,
        }
        self.backend.sitemap.append(entry)

    def _checkpoint(self, reason: str) -> None:
        self.job_state.frontier = self.frontier.to_list()
        self.job_state.in_flight = list(self.in_flight.values())
        self.job_state.visited_url_fingerprints = list(self.visited)
        self.job_state.page_id_map = dict(self.page_id_map)
        self.job_state.counters["queued"] = len(self.frontier)
        self.job_state.last_checkpoint_at = _utc_now()
        self.job_state.updated_at = _utc_now()
        self.backend.job_state.save(self.job_state)
        self.backend.events.log(
            "checkpoint",
            {
                "reason": reason,
                "job_id": self.job_state.job_id,
                "status": self.job_state.status,
                "counters": dict(self.job_state.counters),
                "frontier_size": len(self.frontier),
                "in_flight": len(self.in_flight),
            },
        )

    def _max_pages_reached(self) -> bool:
        if self.config.max_pages is None:
            return False
        fetched = self.job_state.counters.get("fetched", 0)
        return fetched + len(self.in_flight) >= self.config.max_pages


def create_master_app(workspace: Path) -> FastAPI:
    config = load_config(workspace / "config.json")
    backend = create_backend(workspace, config)
    backend.ensure_workspace()

    if not config.distributed.enabled:
        logger.warning("Distributed mode is disabled in config; master will still run.")

    coordinator = MasterCoordinator(workspace, config, backend)

    app = FastAPI(title="Expedition Master")

    @app.post("/register_worker", response_model=RegisterWorkerResponse)
    def register_worker():
        worker_id = coordinator.register_worker()
        return RegisterWorkerResponse(worker_id=worker_id)

    @app.get("/next_task", response_model=TaskResponse)
    def next_task(worker_id: str = Query(...)):
        try:
            task = coordinator.next_task(worker_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if task is None:
            return Response(status_code=204)
        return task

    @app.post("/task_result")
    def task_result(result: TaskResult):
        try:
            coordinator.handle_result(result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "ok"}

    return app


def _request_payload(request_config: RequestConfig) -> RequestPayload:
    return RequestPayload(
        timeout_seconds=request_config.timeout_seconds,
        max_retries=request_config.max_retries,
        retry_backoff_seconds=request_config.retry_backoff_seconds,
        user_agent=request_config.user_agent,
        headers=dict(request_config.headers),
        proxies=request_config.proxies.__dict__,
    )


def _parsing_payload(parsing: ParsingConfig) -> ParsingPayload:
    return ParsingPayload(
        extract_text=parsing.extract_text,
        extract_links=parsing.extract_links,
        max_links_per_page=parsing.max_links_per_page,
    )


def _rendering_payload(rendering: RenderingConfig) -> RenderingPayload:
    return RenderingPayload(
        enabled=rendering.enabled,
        provider=rendering.provider,
        browser=rendering.browser,
        headless=rendering.headless,
        timeout_seconds=rendering.timeout_seconds,
        wait_until=rendering.wait_until,
    )


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
