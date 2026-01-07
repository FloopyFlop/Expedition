from __future__ import annotations

import json
from pathlib import Path

from expedition.config import ExpeditionConfig, write_config
from expedition.hooks import HookRunner
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


def test_hook_annotations_written(local_site: str, tmp_path: Path) -> None:
    workspace = tmp_path / "hooks"
    workspace.mkdir()
    hook_path = tmp_path / "hook.py"
    hook_path.write_text(
        "def process_page(context):\n    return {'tag': 'demo', 'page_id': context.page_id}\n",
        encoding="utf-8",
    )

    config = ExpeditionConfig(
        mode="crawl",
        seed_url=f"{local_site}/index.html",
        traversal="bfs",
        max_depth=0,
        max_pages=1,
    )
    config.parsing.extract_links = False
    config.parsing.extract_text = True
    config.concurrency.max_workers = 1
    config.hooks.enabled = True
    config.hooks.script_path = str(hook_path)
    config.hooks.function = "process_page"
    config.hooks.run_on = "master"

    write_config(workspace / "config.json", config)
    storage = LocalJsonBackend(workspace, config)
    storage.ensure_workspace()

    job_state = _create_job_state()
    storage.job_state.save(job_state)

    hook_runner = HookRunner.from_config(config.hooks, workspace=workspace)
    runner = JobRunner(workspace, config, storage, job_state, hook_runner=hook_runner)
    runner.run()

    metadata_path = workspace / "archive" / "pages" / "00000001" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["annotations"]["tag"] == "demo"
