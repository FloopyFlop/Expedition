from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .config import ExpeditionConfig, SourceConfig


def resolve_sources(config: ExpeditionConfig) -> list[SourceConfig]:
    sources: list[SourceConfig] = []
    sources.extend(config.sources)

    seed_urls = list(config.seed_urls)
    if config.seed_url:
        seed_urls.append(config.seed_url)

    input_files = list(config.input_urls_files)
    if config.input_urls_file:
        input_files.append(config.input_urls_file)

    seed_index = 1
    for seed_url in seed_urls:
        sources.append(
            SourceConfig(
                source_id=f"seed-{seed_index}",
                mode="crawl",
                seed_url=seed_url,
            )
        )
        seed_index += 1

    list_index = 1
    for input_file in input_files:
        sources.append(
            SourceConfig(
                source_id=f"list-{list_index}",
                mode="list",
                input_urls_file=input_file,
            )
        )
        list_index += 1

    if not sources:
        if config.mode == "crawl" and config.seed_url:
            sources.append(SourceConfig(source_id="seed-1", mode="crawl", seed_url=config.seed_url))
        elif config.mode == "list" and config.input_urls_file:
            sources.append(
                SourceConfig(
                    source_id="list-1",
                    mode="list",
                    input_urls_file=config.input_urls_file,
                )
            )

    sources = _ensure_source_ids(sources)
    sources = [_apply_defaults(source, config) for source in sources]
    return sources


def _apply_defaults(source: SourceConfig, config: ExpeditionConfig) -> SourceConfig:
    mode = source.mode or config.mode
    traversal = source.traversal or config.traversal
    return replace(source, mode=mode, traversal=traversal)


def _ensure_source_ids(sources: Iterable[SourceConfig]) -> list[SourceConfig]:
    seen: set[str] = set()
    resolved: list[SourceConfig] = []
    for index, source in enumerate(sources, start=1):
        source_id = source.source_id or f"source-{index}"
        if source_id in seen:
            suffix = 2
            candidate = f"{source_id}-{suffix}"
            while candidate in seen:
                suffix += 1
                candidate = f"{source_id}-{suffix}"
            source_id = candidate
        seen.add(source_id)
        resolved.append(replace(source, source_id=source_id))
    return resolved
