from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path

from fastapi.testclient import TestClient

from expedition.config import ExpeditionConfig, write_config
from expedition.distributed.master import create_master_app
from expedition.job.state import JobState
from expedition.storage.local_json import LocalJsonBackend


def _create_job_state() -> JobState:
    return JobState(
        job_id="job-test",
        status="running",
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


def test_master_worker_flow(local_site: str, tmp_path: Path) -> None:
    workspace = tmp_path / "distributed"
    workspace.mkdir()

    config = ExpeditionConfig(
        mode="crawl",
        seed_url=f"{local_site}/index.html",
        traversal="bfs",
        max_depth=0,
        max_pages=1,
    )
    config.parsing.extract_links = False
    config.parsing.extract_text = False
    config.distributed.enabled = True

    write_config(workspace / "config.json", config)
    backend = LocalJsonBackend(workspace, config)
    backend.ensure_workspace()
    backend.job_state.save(_create_job_state())

    app = create_master_app(workspace)
    client = TestClient(app)

    register_resp = client.post("/register_worker")
    assert register_resp.status_code == 200
    worker_id = register_resp.json()["worker_id"]

    task_resp = client.get("/next_task", params={"worker_id": worker_id})
    assert task_resp.status_code == 200
    task = task_resp.json()

    with urllib.request.urlopen(task["url_normalized"]) as response:
        body = response.read()
        status_code = response.status
        headers = dict(response.headers)
        content_type = response.headers.get("Content-Type")

    result = {
        "task_id": task["task_id"],
        "page_id": task["page_id"],
        "url_original": task["url_original"],
        "url_normalized": task["url_normalized"],
        "final_url": task["url_normalized"],
        "status_code": status_code,
        "headers": headers,
        "body_b64": base64.b64encode(body).decode("ascii"),
        "error": None,
        "content_type": content_type,
        "content_length": len(body),
        "sha256": None,
        "title": None,
        "h1": None,
        "word_count": None,
        "text": None,
        "outlinks": [],
        "proxy_used": None,
    }

    result_resp = client.post("/task_result", json=result)
    assert result_resp.status_code == 200

    next_resp = client.get("/next_task", params={"worker_id": worker_id})
    assert next_resp.status_code == 204

    sitemap_lines = (workspace / "sitemap.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(line) for line in sitemap_lines if line.strip()]
    assert len(entries) == 1
    assert entries[0]["url_normalized"] == task["url_normalized"]
