from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from ..config import ExpeditionConfig, SourceConfig
from ..dedupe import content_hash, url_fingerprint
from ..fetcher import CloudscraperFetcher, ProxySelector
from ..frontier import Frontier
from ..hooks import HookContext, HookRunner, should_run_hook
from ..normalize import normalize_url
from ..parser import ParsedPage, parse_html
from ..renderer import render_html
from ..storage.interfaces import StorageBackend
from ..storage.models import ArchiveWriteRequest, ContentSummary
from ..sources import resolve_sources
from .state import FrontierItem, JobState

logger = logging.getLogger(__name__)


@dataclass
class FetchOutcome:
    item: FrontierItem
    parsed: ParsedPage | None
    error: str | None
    status_code: int | None
    content_type: str | None
    content_length: int | None
    headers: dict[str, str]
    body: bytes
    final_url: str | None
    proxy_used: str | None
    render_error: str | None


class JobRunner:
    def __init__(
        self,
        workspace: Path,
        config: ExpeditionConfig,
        storage: StorageBackend,
        job_state: JobState,
        hook_runner: HookRunner | None = None,
    ) -> None:
        self.workspace = workspace
        self.config = config
        self.storage = storage
        self.job_state = job_state
        self.frontier = Frontier(config.traversal, job_state.frontier)
        self.visited = set(job_state.visited_url_fingerprints)
        self.page_id_map = dict(job_state.page_id_map)
        self.fetcher = CloudscraperFetcher(ProxySelector(config.request.proxies))
        self.archive = storage.archive
        self.hook_runner = hook_runner
        self.sources = resolve_sources(config)
        self.source_status = job_state.source_status
        self._init_source_status()
        self.allow_patterns = [re.compile(p) for p in config.allow_patterns]
        self.deny_patterns = [re.compile(p) for p in config.deny_patterns]
        self._lock = threading.Lock()
        self._pages_since_checkpoint = 0

    def run(self) -> None:
        self.storage.ensure_workspace()
        self._seed_frontier_if_needed()

        if self.job_state.status in {"canceled"}:
            logger.info("Job is canceled; nothing to run.")
            return

        if self._limit_already_reached():
            self._set_status("completed")
            logger.info("Max pages limit already reached.")
            self._checkpoint(force=True)
            return

        self._set_status("running")
        self.storage.job_state.save(self.job_state)
        self.storage.events.log(
            "job_started",
            {"job_id": self.job_state.job_id, "status": self.job_state.status},
        )
        max_workers = max(1, int(self.config.concurrency.max_workers))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            in_flight: dict = {}

            while not self.frontier.is_empty() or in_flight:
                if self._should_stop():
                    logger.info("Stopping after current in-flight tasks.")
                    break

                while (
                    len(in_flight) < max_workers
                    and not self.frontier.is_empty()
                    and not self._should_stop()
                    and not self._max_pages_reached(in_flight)
                ):
                    item = self._next_frontier_item(in_flight)
                    if item is None:
                        break
                    future = executor.submit(self._fetch_item, item)
                    in_flight[future] = item

                if not in_flight:
                    break

                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    item = in_flight.pop(future)
                    outcome = future.result()
                    self._handle_outcome(outcome)

                if self._max_pages_reached(in_flight) and not in_flight:
                    self._set_status("completed")
                    logger.info("Reached max_pages limit.")
                    break

        if self._should_stop():
            logger.info("Job paused or canceled.")
        elif self.frontier.is_empty() or self._limit_already_reached():
            self._set_status("completed")
            logger.info("Job completed.")

        self._checkpoint(force=True)
        self.storage.events.log(
            "job_stopped",
            {
                "job_id": self.job_state.job_id,
                "status": self.job_state.status,
                "counters": dict(self.job_state.counters),
            },
        )

    def _fetch_item(self, item: FrontierItem) -> FetchOutcome:
        result = self.fetcher.fetch(item.url_normalized, self.config.request)
        parsed = None
        render_error: str | None = None
        final_url = result.final_url
        if result.error is None and _is_parsable(result.content_type):
            rendered_html = None
            if self.config.rendering.enabled:
                render_result = render_html(
                    item.url_normalized,
                    self.config.rendering,
                    result.proxy_used,
                )
                if render_result.error:
                    render_error = render_result.error
                if render_result.html:
                    rendered_html = render_result.html
                    if render_result.final_url:
                        final_url = render_result.final_url
            html = rendered_html or result.body.decode("utf-8", errors="replace")
            parsed = parse_html(
                html,
                extract_links=self.config.parsing.extract_links,
                max_links=self.config.parsing.max_links_per_page,
                extract_text=self.config.parsing.extract_text,
            )
        return FetchOutcome(
            item=item,
            parsed=parsed,
            error=result.error,
            status_code=result.status_code,
            content_type=result.content_type,
            content_length=result.content_length,
            headers=result.headers,
            body=result.body,
            final_url=final_url,
            proxy_used=result.proxy_used,
            render_error=render_error,
        )

    def _handle_outcome(self, outcome: FetchOutcome) -> None:
        now = _utc_now()
        item = outcome.item

        if outcome.error:
            logger.warning("Fetch failed for %s: %s", item.url_normalized, outcome.error)
            self.job_state.counters["failed"] = self.job_state.counters.get("failed", 0) + 1
            self._bump_source_counter(item.source_id, "failed", 1)
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
            self.storage.events.log(
                "page_failed",
                {
                    "page_id": item.page_id,
                    "url_normalized": item.url_normalized,
                    "error": outcome.error,
                },
            )
            self._checkpoint_if_needed()
            return

        title = None
        h1 = None
        word_count = None
        summary = None
        outlinks: list[str] = []
        text = None
        annotations = None
        if outcome.parsed:
            title = outcome.parsed.title
            text = outcome.parsed.text
            h1 = outcome.parsed.h1
            word_count = outcome.parsed.word_count
            summary = ContentSummary(title=title, h1=h1, word_count=word_count)
            if self.config.mode == "crawl" and self.config.parsing.extract_links:
                normalized_links = self._normalize_and_filter_links(
                    outcome.parsed.links, outcome.final_url or item.url_normalized
                )
                outlinks = [normalized for _, normalized in normalized_links]
                self._enqueue_links(normalized_links, parent=item)
        if outcome.render_error:
            logger.warning("Render failed for %s: %s", item.url_normalized, outcome.render_error)
            self.storage.events.log(
                "render_failed",
                {
                    "page_id": item.page_id,
                    "url_normalized": item.url_normalized,
                    "error": outcome.render_error,
                },
            )

        if self.hook_runner and should_run_hook(
            self.config.hooks, distributed=False, role="master"
        ):
            context = HookContext(
                workspace=self.workspace,
                source_id=item.source_id,
                page_id=item.page_id,
                url_original=item.url_original,
                url_normalized=item.url_normalized,
                final_url=outcome.final_url,
                fetched_at=now,
                status_code=outcome.status_code,
                content_type=outcome.content_type,
                content_length=outcome.content_length,
                headers=outcome.headers,
                body=outcome.body,
                text=text,
                title=title,
                h1=h1,
                word_count=word_count,
                outlinks=outlinks or None,
                proxy_used=outcome.proxy_used,
            )
            try:
                hook_result = self.hook_runner.run(context)
                annotations = hook_result.annotations
            except Exception as exc:  # pragma: no cover - hook behavior
                logger.warning("Hook failed for %s: %s", item.url_normalized, exc)
                self.storage.events.log(
                    "hook_failed",
                    {
                        "page_id": item.page_id,
                        "url_normalized": item.url_normalized,
                        "error": str(exc),
                    },
                )

        content_sha = content_hash(outcome.body) if outcome.body else None

        self.archive.write_page(
            ArchiveWriteRequest(
                page_id=item.page_id,
                source_id=item.source_id,
                url_original=item.url_original,
                url_normalized=item.url_normalized,
                fetched_at=now,
                request_headers=self._request_headers(),
                response_status=outcome.status_code,
                response_headers=outcome.headers,
                body=outcome.body,
                content_type=outcome.content_type,
                content_hash=content_sha,
                proxy_used=outcome.proxy_used,
                text=text,
                summary=summary,
                annotations=annotations,
            )
        )

        self._append_sitemap_entry(
            item=item,
            fetched_at=now,
            http_status=outcome.status_code,
            content_type=outcome.content_type,
            content_length=outcome.content_length,
            sha256=content_sha,
            title=title,
            outlinks=outlinks or None,
        )

        self.job_state.counters["fetched"] = self.job_state.counters.get("fetched", 0) + 1
        self._bump_source_counter(item.source_id, "fetched", 1)
        self.storage.events.log(
            "page_fetched",
            {
                "page_id": item.page_id,
                "url_normalized": item.url_normalized,
                "status_code": outcome.status_code,
                "content_type": outcome.content_type,
            },
        )
        self._checkpoint_if_needed()

    def _request_headers(self) -> dict[str, str]:
        headers = dict(self.config.request.headers)
        if self.config.request.user_agent:
            headers["User-Agent"] = self.config.request.user_agent
        return headers

    def _enqueue_links(
        self, links: Iterable[tuple[str, str]], parent: FrontierItem
    ) -> None:
        max_depth = self._source_max_depth(parent.source_id)
        if max_depth is not None and parent.depth >= max_depth:
            return

        items: list[FrontierItem] = []
        for original, normalized in links:
            fingerprint = url_fingerprint(normalized)
            if fingerprint in self.visited:
                self.job_state.counters["skipped"] = (
                    self.job_state.counters.get("skipped", 0) + 1
                )
                self._bump_source_counter(parent.source_id, "skipped", 1)
                continue

            page_id = self._get_or_create_page_id(normalized)
            item = FrontierItem(
                url_original=original,
                url_normalized=normalized,
                depth=parent.depth + 1,
                parent_page_id=parent.page_id,
                page_id=page_id,
                discovered_at=_utc_now(),
                source_id=parent.source_id,
            )
            self.visited.add(fingerprint)
            items.append(item)

        if items:
            self.frontier.push_many(items)

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

    def _set_status(self, status: str) -> None:
        self.job_state.status = status
        self.job_state.updated_at = _utc_now()

    def _should_stop(self) -> bool:
        external = self.storage.job_state.read_status()
        if external in {"paused", "canceled"}:
            self.job_state.status = external
            return True
        return self.job_state.status in {"paused", "canceled", "completed"}

    def _max_pages_reached(self, in_flight: dict) -> bool:
        if self.config.max_pages is None:
            return False
        fetched = self.job_state.counters.get("fetched", 0)
        return fetched + len(in_flight) >= self.config.max_pages

    def _limit_already_reached(self) -> bool:
        if self.config.max_pages is None:
            return False
        fetched = self.job_state.counters.get("fetched", 0)
        return fetched >= self.config.max_pages

    def _next_frontier_item(self, in_flight: dict) -> FrontierItem | None:
        while not self.frontier.is_empty():
            item = self.frontier.pop()
            if self._source_max_pages_reached(item.source_id, in_flight):
                self._bump_source_counter(item.source_id, "skipped", 1)
                self.job_state.counters["skipped"] = self.job_state.counters.get("skipped", 0) + 1
                continue
            return item
        return None

    def _source_max_pages_reached(self, source_id: str, in_flight: dict) -> bool:
        max_pages = self._source_max_pages(source_id)
        if max_pages is None:
            return False
        fetched = self._source_counter(source_id, "fetched")
        in_flight_count = sum(
            1 for item in in_flight.values() if item.source_id == source_id
        )
        return fetched + in_flight_count >= max_pages

    def _source_max_pages(self, source_id: str) -> int | None:
        source = self._source_by_id(source_id)
        if source and source.max_pages is not None:
            return source.max_pages
        return None

    def _source_max_depth(self, source_id: str) -> int | None:
        source = self._source_by_id(source_id)
        if source and source.max_depth is not None:
            return source.max_depth
        return self.config.max_depth

    def _source_by_id(self, source_id: str) -> "SourceConfig" | None:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        if source_id == "default":
            return SourceConfig(
                source_id="default",
                mode=self.config.mode,
                seed_url=self.config.seed_url,
                input_urls_file=self.config.input_urls_file,
                traversal=self.config.traversal,
                max_depth=self.config.max_depth,
                max_pages=self.config.max_pages,
            )
        return None

    def _init_source_status(self) -> None:
        for source in self.sources:
            self._ensure_source_state(source.source_id)
        for item in self.frontier.to_list():
            self._mark_source_running(item.source_id)

    def _ensure_source_state(self, source_id: str) -> None:
        if source_id in self.source_status:
            return
        source = self._source_by_id(source_id)
        payload = {
            "status": "pending",
            "mode": source.mode if source else None,
            "seed_url": source.seed_url if source else None,
            "input_urls_file": source.input_urls_file if source else None,
            "max_depth": source.max_depth if source else None,
            "max_pages": source.max_pages if source else None,
            "counters": {"fetched": 0, "skipped": 0, "failed": 0, "queued": 0},
        }
        self.source_status[source_id] = payload

    def _mark_source_running(self, source_id: str) -> None:
        self._ensure_source_state(source_id)
        self.source_status[source_id]["status"] = "running"

    def _mark_source_completed_if_done(self) -> None:
        if not self.sources:
            return
        source_queue_counts: dict[str, int] = {
            source.source_id: 0 for source in self.sources
        }
        for item in self.frontier.to_list():
            source_queue_counts[item.source_id] = source_queue_counts.get(item.source_id, 0) + 1
        for source_id, count in source_queue_counts.items():
            self._ensure_source_state(source_id)
            self.source_status[source_id]["counters"]["queued"] = count
            status = self.source_status[source_id].get("status")
            if count == 0 and status == "running":
                self.source_status[source_id]["status"] = "completed"

    def _source_counter(self, source_id: str, key: str) -> int:
        self._ensure_source_state(source_id)
        counters = self.source_status[source_id].setdefault(
            "counters", {"fetched": 0, "skipped": 0, "failed": 0, "queued": 0}
        )
        return int(counters.get(key, 0))

    def _bump_source_counter(self, source_id: str, key: str, amount: int) -> None:
        self._ensure_source_state(source_id)
        counters = self.source_status[source_id].setdefault(
            "counters", {"fetched": 0, "skipped": 0, "failed": 0, "queued": 0}
        )
        counters[key] = int(counters.get(key, 0)) + amount

    def _checkpoint_if_needed(self) -> None:
        self._pages_since_checkpoint += 1
        if self._pages_since_checkpoint >= self.config.checkpoint_interval:
            self._checkpoint(force=False)
            self._pages_since_checkpoint = 0

    def _checkpoint(self, *, force: bool) -> None:
        with self._lock:
            self.job_state.frontier = self.frontier.to_list()
            self.job_state.in_flight = []
            self.job_state.visited_url_fingerprints = list(self.visited)
            self.job_state.page_id_map = dict(self.page_id_map)
            self.job_state.counters["queued"] = len(self.frontier)
            self._mark_source_completed_if_done()
            if force or self.config.checkpoint_interval >= 1:
                self.job_state.last_checkpoint_at = _utc_now()
            self.job_state.updated_at = _utc_now()
            self.storage.job_state.save(self.job_state)
            self.storage.events.log(
                "checkpoint",
                {
                    "job_id": self.job_state.job_id,
                    "status": self.job_state.status,
                    "counters": dict(self.job_state.counters),
                    "frontier_size": len(self.frontier),
                },
            )
            logger.info(
                "Progress fetched=%s skipped=%s failed=%s queued=%s",
                self.job_state.counters.get("fetched", 0),
                self.job_state.counters.get("skipped", 0),
                self.job_state.counters.get("failed", 0),
                self.job_state.counters.get("queued", 0),
            )

    def _seed_frontier_if_needed(self) -> None:
        if self.frontier.to_list() or self.visited:
            return
        if not self.sources:
            raise ValueError("No sources configured. Provide seed_url(s) or input_urls_file(s).")

        for source in self.sources:
            self._ensure_source_state(source.source_id)
            if source.mode == "crawl":
                if not source.seed_url:
                    raise ValueError(f"seed_url is required for source {source.source_id}")
                normalized = normalize_url(
                    source.seed_url,
                    drop_query_param_prefixes=self.config.normalize.drop_query_param_prefixes,
                )
                if not normalized:
                    continue
                page_id = self._get_or_create_page_id(normalized)
                item = FrontierItem(
                    url_original=source.seed_url,
                    url_normalized=normalized,
                    depth=0,
                    parent_page_id=None,
                    page_id=page_id,
                    discovered_at=_utc_now(),
                    source_id=source.source_id,
                )
                if url_fingerprint(normalized) in self.visited:
                    self._bump_source_counter(source.source_id, "skipped", 1)
                    self.job_state.counters["skipped"] = (
                        self.job_state.counters.get("skipped", 0) + 1
                    )
                    continue
                self.frontier.push(item)
                self.visited.add(url_fingerprint(normalized))
                self._mark_source_running(source.source_id)
                continue

            if source.mode == "list":
                urls = self._read_input_urls(source)
                items: list[FrontierItem] = []
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
                        self._bump_source_counter(source.source_id, "skipped", 1)
                        self.job_state.counters["skipped"] = (
                            self.job_state.counters.get("skipped", 0) + 1
                        )
                        continue
                    page_id = self._get_or_create_page_id(normalized)
                    items.append(
                        FrontierItem(
                            url_original=url,
                            url_normalized=normalized,
                            depth=0,
                            parent_page_id=None,
                            page_id=page_id,
                            discovered_at=_utc_now(),
                            source_id=source.source_id,
                        )
                    )
                    self.visited.add(fingerprint)
                if items:
                    self.frontier.push_many(items)
                    self._mark_source_running(source.source_id)
                continue

            raise ValueError(f"Unknown source mode: {source.mode}")

    def _read_input_urls(self, source: SourceConfig) -> list[str]:
        if not source.input_urls_file:
            raise ValueError(f"input_urls_file is required for source {source.source_id}")
        path = Path(source.input_urls_file)
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
            "source_id": item.source_id,
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
        self.storage.sitemap.append(entry)


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _is_parsable(content_type: str | None) -> bool:
    if not content_type:
        return False
    lower_type = content_type.lower()
    return "html" in lower_type or lower_type.startswith("text/")
