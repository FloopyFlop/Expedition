from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from expedition import (
    ExpeditionConfig,
    get_status,
    init_workspace,
    load_workspace,
    run_workspace,
)

from .config import EmbarkConfig


def main() -> None:
    parser = argparse.ArgumentParser(prog="embark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize an Embark workspace")
    _add_workspace_arg(init_parser)
    _add_embark_args(init_parser)

    run_parser = subparsers.add_parser("run", help="Run an Embark crawl")
    _add_workspace_arg(run_parser)

    status_parser = subparsers.add_parser("status", help="Show Embark job status")
    _add_workspace_arg(status_parser)

    args = parser.parse_args()
    workspace = Path(args.workspace)

    if args.command == "init":
        config = _build_expedition_config(args)
        embark_config = _build_embark_config(args)
        init_workspace(workspace, config, overwrite=bool(args.overwrite))
        embark_config.save(workspace)
        _print_init_summary(workspace, config, embark_config)
        return

    if args.command == "run":
        run_workspace(workspace)
        return

    if args.command == "status":
        status = get_status(workspace)
        print(json.dumps(status, indent=2, sort_keys=True))
        return


def _add_workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, help="Workspace directory")


def _add_embark_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--mode", choices=["crawl", "list"], default="crawl")
    parser.add_argument("--seed-url", dest="seed_url")
    parser.add_argument("--input-urls-file", dest="input_urls_file")
    parser.add_argument("--traversal", choices=["bfs", "dfs"], default="bfs")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--allowed-domain", action="append", default=[])
    parser.add_argument("--allow-pattern", action="append", default=[])
    parser.add_argument("--deny-pattern", action="append", default=[])
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--proxy")
    parser.add_argument("--hook-run-on", choices=["auto", "master", "worker", "both"], default="master")

    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--ollama-model", default="llama3")
    parser.add_argument("--ollama-timeout", type=int, default=60)
    parser.add_argument("--max-input-chars", type=int, default=8000)


def _build_expedition_config(args: argparse.Namespace) -> ExpeditionConfig:
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
    )
    config.parsing.extract_links = True
    config.parsing.extract_text = True
    config.concurrency.max_workers = args.max_workers

    if args.proxy:
        config.request.proxies.enabled = True
        config.request.proxies.http = args.proxy
        config.request.proxies.https = args.proxy

    config.hooks.enabled = True
    config.hooks.callable = "embark.hook:process_page"
    config.hooks.run_on = args.hook_run_on

    return config


def _build_embark_config(args: argparse.Namespace) -> EmbarkConfig:
    return EmbarkConfig(
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        timeout_seconds=args.ollama_timeout,
        max_input_chars=args.max_input_chars,
    )


def _print_init_summary(
    workspace: Path, config: ExpeditionConfig, embark_config: EmbarkConfig
) -> None:
    summary = {
        "workspace": str(workspace),
        "expedition_config": asdict(config),
        "embark_config": embark_config.to_dict(),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
