from __future__ import annotations

import json
from pathlib import Path

from expedition.config import ExpeditionConfig, write_config
from expedition.job.runner import JobRunner
from expedition.job.state import JobState
from expedition.storage.local_json import LocalJsonBackend


def _create_job_state() -> JobState:
    return JobState(
        job_id="job-test",
        status="paused",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        frontier=[],
        in_flight=[],
        visited_url_fingerprints=[],
        page_id_map={},
        counters={"fetched": 0, "skipped": 0, "failed": 0, "queued": 0},
        next_page_id=1,
        last_checkpoint_at=None,
    )


def _run_crawl(
    workspace: Path, base_url: str, traversal: str, max_pages: int | None = None
) -> Path:
    config = ExpeditionConfig(
        mode="crawl",
        seed_url=f"{base_url}/index.html",
        traversal=traversal,
        max_depth=2,
        max_pages=max_pages,
    )
    config.parsing.extract_links = True
    config.parsing.extract_text = False
    config.concurrency.max_workers = 1

    write_config(workspace / "config.json", config)
    storage = LocalJsonBackend(workspace, config)
    storage.ensure_workspace()

    job_state = _create_job_state()
    storage.job_state.save(job_state)

    runner = JobRunner(workspace, config, storage, job_state)
    runner.run()
    return workspace


def _read_sitemap(workspace: Path) -> list[dict[str, object]]:
    lines = (workspace / "sitemap.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_bfs_order(local_site: str, tmp_path: Path) -> None:
    workspace = tmp_path / "bfs"
    workspace.mkdir()
    _run_crawl(workspace, local_site, traversal="bfs")
    entries = _read_sitemap(workspace)

    expected = [
        f"{local_site}/index.html",
        f"{local_site}/a.html",
        f"{local_site}/b.html",
        f"{local_site}/a1.html",
        f"{local_site}/b1.html",
    ]
    assert [entry["url_normalized"] for entry in entries] == expected


def test_dfs_order(local_site: str, tmp_path: Path) -> None:
    workspace = tmp_path / "dfs"
    workspace.mkdir()
    _run_crawl(workspace, local_site, traversal="dfs")
    entries = _read_sitemap(workspace)

    expected = [
        f"{local_site}/index.html",
        f"{local_site}/a.html",
        f"{local_site}/a1.html",
        f"{local_site}/b.html",
        f"{local_site}/b1.html",
    ]
    assert [entry["url_normalized"] for entry in entries] == expected


def test_resume(local_site: str, tmp_path: Path) -> None:
    workspace = tmp_path / "resume"
    workspace.mkdir()

    _run_crawl(workspace, local_site, traversal="bfs", max_pages=1)
    entries_after_first = _read_sitemap(workspace)
    assert len(entries_after_first) == 1

    config = ExpeditionConfig(
        mode="crawl",
        seed_url=f"{local_site}/index.html",
        traversal="bfs",
        max_depth=2,
        max_pages=None,
    )
    config.parsing.extract_links = True
    config.parsing.extract_text = False
    config.concurrency.max_workers = 1
    write_config(workspace / "config.json", config)

    storage = LocalJsonBackend(workspace, config)
    job_state = storage.job_state.load()
    job_state.status = "running"
    storage.job_state.save(job_state)

    runner = JobRunner(workspace, config, storage, job_state)
    runner.run()

    entries_after_resume = _read_sitemap(workspace)
    assert len(entries_after_resume) == 5
