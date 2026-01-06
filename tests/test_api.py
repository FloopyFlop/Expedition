from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from expedition.api import create_app
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


def _run_single_page(workspace: Path, base_url: str) -> None:
    config = ExpeditionConfig(
        mode="crawl",
        seed_url=f"{base_url}/index.html",
        traversal="bfs",
        max_depth=0,
        max_pages=1,
    )
    config.parsing.extract_links = False
    config.parsing.extract_text = False
    config.concurrency.max_workers = 1

    write_config(workspace / "config.json", config)
    backend = LocalJsonBackend(workspace, config)
    backend.ensure_workspace()

    job_state = _create_job_state()
    backend.job_state.save(job_state)

    runner = JobRunner(workspace, config, backend, job_state)
    runner.run()


def test_api_endpoints(local_site: str, tmp_path: Path) -> None:
    workspace = tmp_path / "api"
    workspace.mkdir()
    _run_single_page(workspace, local_site)

    app = create_app(workspace)
    client = TestClient(app)

    sitemap_resp = client.get("/sitemap")
    assert sitemap_resp.status_code == 200
    items = sitemap_resp.json()["items"]
    assert len(items) == 1

    page_id = items[0]["page_id"]
    page_resp = client.get(f"/pages/{page_id}")
    assert page_resp.status_code == 200
    payload = page_resp.json()
    assert payload["metadata"]["page_id"] == page_id

    body_resp = client.get(f"/pages/{page_id}/body")
    assert body_resp.status_code == 200
    assert body_resp.content
