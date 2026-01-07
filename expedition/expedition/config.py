from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProxyConfig:
    enabled: bool = False
    http: str | None = None
    https: str | None = None
    rotate: bool = False
    pool: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ProxyConfig":
        explicit_enabled = data.get("enabled")
        http = data.get("http")
        https = data.get("https")
        pool = list(data.get("pool", []))
        has_proxy = bool(http or https or pool)
        enabled = bool(explicit_enabled) if explicit_enabled is not None else has_proxy
        if has_proxy and not enabled:
            enabled = True
        return ProxyConfig(
            enabled=enabled,
            http=http,
            https=https,
            rotate=bool(data.get("rotate", False)),
            pool=pool,
        )


@dataclass
class SourceConfig:
    source_id: str | None = None
    mode: str | None = None
    seed_url: str | None = None
    input_urls_file: str | None = None
    traversal: str | None = None
    max_depth: int | None = None
    max_pages: int | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SourceConfig":
        max_pages = data.get("max_pages")
        if max_pages is not None:
            max_pages = int(max_pages)
        max_depth = data.get("max_depth")
        if max_depth is not None:
            max_depth = int(max_depth)
        return SourceConfig(
            source_id=data.get("source_id"),
            mode=data.get("mode"),
            seed_url=data.get("seed_url"),
            input_urls_file=data.get("input_urls_file"),
            traversal=data.get("traversal"),
            max_depth=max_depth,
            max_pages=max_pages,
        )


@dataclass
class RequestConfig:
    timeout_seconds: int = 15
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    user_agent: str = "Expedition/0.1 (local)"
    headers: dict[str, str] = field(default_factory=dict)
    proxies: ProxyConfig = field(default_factory=ProxyConfig)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RequestConfig":
        return RequestConfig(
            timeout_seconds=int(data.get("timeout_seconds", 15)),
            max_retries=int(data.get("max_retries", 2)),
            retry_backoff_seconds=float(data.get("retry_backoff_seconds", 1.0)),
            user_agent=str(data.get("user_agent", "Expedition/0.1 (local)")),
            headers=dict(data.get("headers", {})),
            proxies=ProxyConfig.from_dict(data.get("proxies", {})),
        )


@dataclass
class ParsingConfig:
    extract_text: bool = False
    extract_links: bool = True
    max_links_per_page: int | None = 200

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ParsingConfig":
        return ParsingConfig(
            extract_text=bool(data.get("extract_text", False)),
            extract_links=bool(data.get("extract_links", True)),
            max_links_per_page=data.get("max_links_per_page", 200),
        )


@dataclass
class ConcurrencyConfig:
    max_workers: int = 4
    per_host_limit: int | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ConcurrencyConfig":
        return ConcurrencyConfig(
            max_workers=int(data.get("max_workers", 4)),
            per_host_limit=data.get("per_host_limit"),
        )


@dataclass
class DistributedConfig:
    enabled: bool = False
    master_url: str | None = None
    worker_poll_interval_seconds: float = 2.0

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DistributedConfig":
        return DistributedConfig(
            enabled=bool(data.get("enabled", False)),
            master_url=data.get("master_url"),
            worker_poll_interval_seconds=float(data.get("worker_poll_interval_seconds", 2.0)),
        )


@dataclass
class RenderingConfig:
    enabled: bool = False
    provider: str = "playwright"
    browser: str = "chromium"
    headless: bool = True
    timeout_seconds: int = 20
    wait_until: str = "load"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RenderingConfig":
        return RenderingConfig(
            enabled=bool(data.get("enabled", False)),
            provider=str(data.get("provider", "playwright")),
            browser=str(data.get("browser", "chromium")),
            headless=bool(data.get("headless", True)),
            timeout_seconds=int(data.get("timeout_seconds", 20)),
            wait_until=str(data.get("wait_until", "load")),
        )


@dataclass
class HookConfig:
    enabled: bool = False
    script_path: str | None = None
    callable: str | None = None
    function: str = "process_page"
    run_on: str = "auto"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "HookConfig":
        script_path = data.get("script_path")
        callable_path = data.get("callable")
        explicit_enabled = data.get("enabled")
        has_hook = bool(script_path or callable_path)
        enabled = bool(explicit_enabled) if explicit_enabled is not None else has_hook
        if has_hook and not enabled:
            enabled = True
        return HookConfig(
            enabled=enabled,
            script_path=script_path,
            callable=callable_path,
            function=str(data.get("function", "process_page")),
            run_on=str(data.get("run_on", "auto")),
        )


@dataclass
class NormalizationConfig:
    drop_query_param_prefixes: list[str] = field(
        default_factory=lambda: ["utm_", "fbclid", "gclid"]
    )

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "NormalizationConfig":
        prefixes = data.get("drop_query_param_prefixes")
        return NormalizationConfig(
            drop_query_param_prefixes=list(prefixes)
            if prefixes is not None
            else ["utm_", "fbclid", "gclid"]
        )


@dataclass
class StorageConfig:
    type: str = "local_json"
    job_state_file: str = "job_state.json"
    sitemap_file: str = "sitemap.jsonl"
    archive_dir: str = "archive"
    logs_dir: str = "logs"
    events_file: str = "events.jsonl"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "StorageConfig":
        return StorageConfig(
            type=str(data.get("type", "local_json")),
            job_state_file=str(data.get("job_state_file", "job_state.json")),
            sitemap_file=str(data.get("sitemap_file", "sitemap.jsonl")),
            archive_dir=str(data.get("archive_dir", "archive")),
            logs_dir=str(data.get("logs_dir", "logs")),
            events_file=str(data.get("events_file", "events.jsonl")),
        )


@dataclass
class ExpeditionConfig:
    mode: str = "crawl"
    seed_url: str | None = None
    seed_urls: list[str] = field(default_factory=list)
    input_urls_file: str | None = None
    input_urls_files: list[str] = field(default_factory=list)
    sources: list[SourceConfig] = field(default_factory=list)
    traversal: str = "bfs"
    max_depth: int = 2
    max_pages: int | None = None
    allowed_domains: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)
    allow_patterns: list[str] = field(default_factory=list)
    obey_robots_txt: bool = False
    checkpoint_interval: int = 1
    request: RequestConfig = field(default_factory=RequestConfig)
    parsing: ParsingConfig = field(default_factory=ParsingConfig)
    concurrency: ConcurrencyConfig = field(default_factory=ConcurrencyConfig)
    distributed: DistributedConfig = field(default_factory=DistributedConfig)
    rendering: RenderingConfig = field(default_factory=RenderingConfig)
    hooks: HookConfig = field(default_factory=HookConfig)
    normalize: NormalizationConfig = field(default_factory=NormalizationConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ExpeditionConfig":
        max_pages = data.get("max_pages")
        if max_pages is not None:
            max_pages = int(max_pages)
        seed_urls = list(data.get("seed_urls", []))
        input_urls_files = list(data.get("input_urls_files", []))
        sources_data = data.get("sources", [])
        sources = [SourceConfig.from_dict(item) for item in sources_data]
        return ExpeditionConfig(
            mode=str(data.get("mode", "crawl")),
            seed_url=data.get("seed_url"),
            seed_urls=seed_urls,
            input_urls_file=data.get("input_urls_file"),
            input_urls_files=input_urls_files,
            sources=sources,
            traversal=str(data.get("traversal", "bfs")),
            max_depth=int(data.get("max_depth", 2)),
            max_pages=max_pages,
            allowed_domains=list(data.get("allowed_domains", [])),
            deny_patterns=list(data.get("deny_patterns", [])),
            allow_patterns=list(data.get("allow_patterns", [])),
            obey_robots_txt=bool(data.get("obey_robots_txt", False)),
            checkpoint_interval=int(data.get("checkpoint_interval", 1)),
            request=RequestConfig.from_dict(data.get("request", {})),
            parsing=ParsingConfig.from_dict(data.get("parsing", {})),
            concurrency=ConcurrencyConfig.from_dict(data.get("concurrency", {})),
            distributed=DistributedConfig.from_dict(data.get("distributed", {})),
            rendering=RenderingConfig.from_dict(data.get("rendering", {})),
            hooks=HookConfig.from_dict(data.get("hooks", {})),
            normalize=NormalizationConfig.from_dict(data.get("normalize", {})),
            storage=StorageConfig.from_dict(data.get("storage", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoragePaths:
    job_state_path: Path
    sitemap_path: Path
    archive_dir: Path
    logs_dir: Path
    events_path: Path


def resolve_storage_paths(workspace: Path, storage: StorageConfig) -> StoragePaths:
    return StoragePaths(
        job_state_path=workspace / storage.job_state_file,
        sitemap_path=workspace / storage.sitemap_file,
        archive_dir=workspace / storage.archive_dir,
        logs_dir=workspace / storage.logs_dir,
        events_path=workspace / storage.logs_dir / storage.events_file,
    )


def load_config(path: Path) -> ExpeditionConfig:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return ExpeditionConfig.from_dict(data)


def write_config(path: Path, config: ExpeditionConfig) -> None:
    atomic_write_json(path, config.to_dict())


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, path)
