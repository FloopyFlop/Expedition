from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ExpeditionConfig, HookConfig, load_config, resolve_storage_paths, write_config
from .hooks import HookRunner, PageHook, should_run_hook
from .job.runner import JobRunner
from .job.state import JobState
from .logging import configure_logging
from .storage.factory import create_backend
from .storage.interfaces import StorageBackend


def init_workspace(
    workspace: Path | str,
    config: ExpeditionConfig,
    *,
    overwrite: bool = False,
) -> JobState:
    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    config_path = workspace_path / "config.json"

    if config_path.exists() and not overwrite:
        raise FileExistsError(f"Config already exists: {config_path}")

    write_config(config_path, config)
    backend = create_backend(workspace_path, config)
    backend.ensure_workspace()

    now = _utc_now()
    job_state = JobState(
        job_id=_new_job_id(),
        status="paused",
        created_at=now,
        updated_at=now,
        frontier=[],
        in_flight=[],
        visited_url_fingerprints=[],
        page_id_map={},
        counters={"fetched": 0, "skipped": 0, "failed": 0, "queued": 0},
        next_page_id=1,
        last_checkpoint_at=None,
    )
    backend.job_state.save(job_state)
    return job_state


def load_workspace(
    workspace: Path | str,
) -> tuple[ExpeditionConfig, StorageBackend, JobState]:
    workspace_path = Path(workspace)
    config = load_config(workspace_path / "config.json")
    backend = create_backend(workspace_path, config)
    job_state = backend.job_state.load()
    return config, backend, job_state


def run_workspace(
    workspace: Path | str,
    *,
    hook: PageHook | HookRunner | None = None,
) -> JobState:
    workspace_path = Path(workspace)
    config, backend, job_state = load_workspace(workspace_path)
    log_path = resolve_storage_paths(workspace_path, config.storage).logs_dir / "expedition.log"
    configure_logging(log_path)
    hook_runner = None
    if hook:
        hook_runner = hook if isinstance(hook, HookRunner) else HookRunner(
            hook, config=HookConfig(enabled=True, run_on="master")
        )
    elif should_run_hook(config.hooks, distributed=False, role="master"):
        hook_runner = HookRunner.from_config(config.hooks, workspace=workspace_path)
    runner = JobRunner(workspace_path, config, backend, job_state, hook_runner=hook_runner)
    runner.run()
    return backend.job_state.load()


def pause_workspace(workspace: Path | str) -> JobState:
    return _set_status(workspace, "paused")


def resume_workspace(workspace: Path | str, *, run: bool = True) -> JobState:
    state = _set_status(workspace, "running")
    if run:
        run_workspace(workspace)
        state = load_workspace(workspace)[2]
    return state


def cancel_workspace(workspace: Path | str) -> JobState:
    return _set_status(workspace, "canceled")


def get_status(workspace: Path | str) -> dict[str, Any]:
    _, _, job_state = load_workspace(workspace)
    return {
        "job_id": job_state.job_id,
        "status": job_state.status,
        "created_at": job_state.created_at,
        "updated_at": job_state.updated_at,
        "frontier_size": len(job_state.frontier),
        "counters": job_state.counters,
    }


def _set_status(workspace: Path | str, status: str) -> JobState:
    workspace_path = Path(workspace)
    config = load_config(workspace_path / "config.json")
    backend = create_backend(workspace_path, config)
    job_state = backend.job_state.load()
    job_state.status = status
    job_state.updated_at = _utc_now()
    backend.job_state.save(job_state)
    return job_state


def _new_job_id() -> str:
    return f"job-{uuid.uuid4()}"


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
