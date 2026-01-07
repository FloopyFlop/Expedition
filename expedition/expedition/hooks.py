from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import HookConfig


@dataclass
class HookContext:
    workspace: Path
    source_id: str
    page_id: str
    url_original: str
    url_normalized: str
    final_url: str | None
    fetched_at: str
    status_code: int | None
    content_type: str | None
    content_length: int | None
    headers: dict[str, str]
    body: bytes
    text: str | None
    title: str | None
    h1: str | None
    word_count: int | None
    outlinks: list[str] | None
    proxy_used: str | None


@dataclass
class HookResult:
    annotations: dict[str, Any] | None = None


PageHook = Callable[[HookContext], HookResult | dict[str, Any] | None]


class HookRunner:
    def __init__(self, hook: PageHook, *, config: HookConfig) -> None:
        self._hook = hook
        self.config = config

    def run(self, context: HookContext) -> HookResult:
        result = self._hook(context)
        if isinstance(result, HookResult):
            return result
        if isinstance(result, dict):
            return HookResult(annotations=result)
        return HookResult(annotations=None)

    @staticmethod
    def from_config(config: HookConfig, *, workspace: Path) -> HookRunner | None:
        if not config.enabled:
            return None
        hook_callable = _load_hook_callable(config, workspace)
        if not hook_callable:
            return None
        return HookRunner(hook_callable, config=config)


def should_run_hook(config: HookConfig, *, distributed: bool, role: str) -> bool:
    if not config.enabled:
        return False
    run_on = (config.run_on or "auto").lower()
    if role not in {"master", "worker"}:
        raise ValueError(f"Unknown hook role: {role}")

    if run_on == "both":
        return True

    if distributed:
        if run_on == "worker":
            return role == "worker"
        if run_on == "master":
            return role == "master"
        if run_on == "auto":
            return role == "worker"
        return False

    # Single-node master process.
    if run_on in {"auto", "master"}:
        return role == "master"
    return False


def _load_hook_callable(config: HookConfig, workspace: Path) -> PageHook | None:
    if config.callable:
        module_path, _, func_name = config.callable.partition(":")
        if not module_path or not func_name:
            raise ValueError("hooks.callable must be in the form 'module:function'")
        module = importlib.import_module(module_path)
        hook = getattr(module, func_name, None)
        if hook is None:
            raise AttributeError(f"Hook function '{func_name}' not found in {module_path}")
        return hook

    if not config.script_path:
        return None

    path = Path(config.script_path)
    if not path.is_absolute():
        path = workspace / path
    if not path.exists():
        raise FileNotFoundError(str(path))

    module_name = f"expedition_hook_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load hook module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hook = getattr(module, config.function, None)
    if hook is None:
        raise AttributeError(
            f"Hook function '{config.function}' not found in {path}"
        )
    return hook
