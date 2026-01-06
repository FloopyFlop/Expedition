from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import ExpeditionConfig, load_config, resolve_storage_paths, write_config
from .api import create_app
from .distributed.master import create_master_app
from .distributed.worker import WorkerClient
from .job.runner import JobRunner
from .job.state import JobState
from .logging import configure_logging
from .storage.factory import create_backend


def main() -> None:
    parser = argparse.ArgumentParser(prog="expedition")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a workspace")
    _add_workspace_arg(init_parser)
    _add_config_args(init_parser)

    run_parser = subparsers.add_parser("run", help="Run a job in a workspace")
    _add_workspace_arg(run_parser)

    pause_parser = subparsers.add_parser("pause", help="Pause a job")
    _add_workspace_arg(pause_parser)

    resume_parser = subparsers.add_parser("resume", help="Resume a paused job")
    _add_workspace_arg(resume_parser)

    cancel_parser = subparsers.add_parser("cancel", help="Cancel a job")
    _add_workspace_arg(cancel_parser)

    status_parser = subparsers.add_parser("status", help="Show job status")
    _add_workspace_arg(status_parser)

    serve_parser = subparsers.add_parser("serve", help="Serve archive API")
    _add_workspace_arg(serve_parser)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    master_parser = subparsers.add_parser("master", help="Run distributed master")
    _add_workspace_arg(master_parser)
    master_parser.add_argument("--host", default="127.0.0.1")
    master_parser.add_argument("--port", type=int, default=8001)

    worker_parser = subparsers.add_parser("worker", help="Run distributed worker")
    _add_workspace_arg(worker_parser)
    worker_parser.add_argument("--master", dest="master_url")
    worker_parser.add_argument("--poll-interval", type=float)

    args = parser.parse_args()
    workspace = Path(args.workspace)

    if args.command == "init":
        config = _build_config_from_args(args)
        _init_workspace(workspace, config)
        return

    if args.command == "run":
        _run_workspace(workspace)
        return

    if args.command == "pause":
        _set_status(workspace, "paused")
        return

    if args.command == "resume":
        _set_status(workspace, "running")
        _run_workspace(workspace)
        return

    if args.command == "cancel":
        _set_status(workspace, "canceled")
        return

    if args.command == "status":
        _print_status(workspace)
        return

    if args.command == "serve":
        _serve_workspace(workspace, host=args.host, port=args.port)
        return

    if args.command == "master":
        _serve_master(workspace, host=args.host, port=args.port)
        return

    if args.command == "worker":
        _run_worker(workspace, master_url=args.master_url, poll_interval=args.poll_interval)
        return


def _add_workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, help="Workspace directory")


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=["crawl", "list"], default="crawl")
    parser.add_argument("--seed-url", dest="seed_url")
    parser.add_argument("--input-urls-file", dest="input_urls_file")
    parser.add_argument("--traversal", choices=["bfs", "dfs"], default="bfs")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--allowed-domain", action="append", default=[])
    parser.add_argument("--allow-pattern", action="append", default=[])
    parser.add_argument("--deny-pattern", action="append", default=[])
    parser.add_argument("--checkpoint-interval", type=int, default=1)

    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff", type=float, default=1.0)
    parser.add_argument("--user-agent", default="Expedition/0.1 (local)")
    parser.add_argument("--header", action="append", default=[])

    parser.add_argument("--extract-text", action="store_true")
    parser.add_argument("--no-extract-links", action="store_true")
    parser.add_argument("--max-links-per-page", type=int, default=200)

    parser.add_argument("--max-workers", type=int, default=4)


def _build_config_from_args(args: argparse.Namespace) -> ExpeditionConfig:
    config = ExpeditionConfig(
        mode=args.mode,
        seed_url=args.seed_url,
        input_urls_file=args.input_urls_file,
        traversal=args.traversal,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        allowed_domains=args.allowed_domain,
        allow_patterns=args.allow_pattern,
        deny_patterns=args.deny_pattern,
        checkpoint_interval=args.checkpoint_interval,
    )

    config.request.timeout_seconds = args.timeout
    config.request.max_retries = args.max_retries
    config.request.retry_backoff_seconds = args.retry_backoff
    config.request.user_agent = args.user_agent
    config.request.headers = _parse_headers(args.header)

    config.parsing.extract_text = bool(args.extract_text)
    config.parsing.extract_links = not bool(args.no_extract_links)
    config.parsing.max_links_per_page = args.max_links_per_page

    config.concurrency.max_workers = args.max_workers

    return config


def _parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in values:
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def _init_workspace(workspace: Path, config: ExpeditionConfig) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    config_path = workspace / "config.json"
    if config_path.exists():
        raise FileExistsError(f"Config already exists: {config_path}")

    write_config(config_path, config)
    backend = create_backend(workspace, config)
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

    _print_init_summary(workspace, config)


def _run_workspace(workspace: Path) -> None:
    config = load_config(workspace / "config.json")
    backend = create_backend(workspace, config)
    job_state = backend.job_state.load()
    configure_logging(resolve_storage_paths(workspace, config.storage).logs_dir / "expedition.log")

    runner = JobRunner(workspace, config, backend, job_state)
    runner.run()


def _set_status(workspace: Path, status: str) -> None:
    config = load_config(workspace / "config.json")
    backend = create_backend(workspace, config)
    job_state = backend.job_state.load()
    job_state.status = status
    job_state.updated_at = _utc_now()
    backend.job_state.save(job_state)
    print(f"Job status set to {status}.")


def _print_status(workspace: Path) -> None:
    config = load_config(workspace / "config.json")
    backend = create_backend(workspace, config)
    job_state = backend.job_state.load()

    summary = {
        "job_id": job_state.job_id,
        "status": job_state.status,
        "created_at": job_state.created_at,
        "updated_at": job_state.updated_at,
        "frontier_size": len(job_state.frontier),
        "counters": job_state.counters,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def _print_init_summary(workspace: Path, config: ExpeditionConfig) -> None:
    summary = {
        "workspace": str(workspace),
        "config": asdict(config),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _new_job_id() -> str:
    return f"job-{uuid.uuid4()}"


def _serve_workspace(workspace: Path, host: str, port: int) -> None:
    import uvicorn

    app = create_app(workspace)
    uvicorn.run(app, host=host, port=port)


def _serve_master(workspace: Path, host: str, port: int) -> None:
    import uvicorn

    config = load_config(workspace / "config.json")
    configure_logging(resolve_storage_paths(workspace, config.storage).logs_dir / "expedition.log")
    app = create_master_app(workspace)
    uvicorn.run(app, host=host, port=port)


def _run_worker(workspace: Path, master_url: str | None, poll_interval: float | None) -> None:
    if not master_url:
        config = load_config(workspace / "config.json")
        master_url = config.distributed.master_url
        if poll_interval is None:
            poll_interval = config.distributed.worker_poll_interval_seconds
    if not master_url:
        raise ValueError("master URL is required (use --master or config.json)")
    if poll_interval is None:
        poll_interval = 2.0
    worker = WorkerClient(master_url=master_url, workspace=workspace, poll_interval=poll_interval)
    worker.run()
