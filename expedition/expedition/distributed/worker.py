from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from ..config import HookConfig, RenderingConfig, RequestConfig
from ..dedupe import content_hash
from ..fetcher import CloudscraperFetcher, ProxySelector
from ..hooks import HookContext, HookRunner, should_run_hook
from ..logging import configure_logging
from ..parser import parse_html
from ..renderer import render_html
from .protocol import TaskResponse, TaskResult

logger = logging.getLogger(__name__)


class WorkerClient:
    def __init__(
        self,
        *,
        master_url: str,
        workspace: Path,
        poll_interval: float,
    ) -> None:
        self.master_url = master_url.rstrip("/")
        self.workspace = workspace
        self.poll_interval = poll_interval
        self.worker_id: str | None = None

    def run(self, stop_event: Event | None = None) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        log_path = self.workspace / "logs" / "worker.log"
        configure_logging(log_path)
        self.worker_id = self._register_worker()
        logger.info("Registered worker %s", self.worker_id)

        while True:
            if stop_event and stop_event.is_set():
                logger.info("Worker stop event set; exiting.")
                return
            task = self._next_task()
            if task is None:
                time.sleep(self.poll_interval)
                continue

            result = self._process_task(task)
            self._post_result(result)

    def _register_worker(self) -> str:
        url = f"{self.master_url}/register_worker"
        response = _post_json(url, {})
        worker_id = response.get("worker_id")
        if not worker_id:
            raise RuntimeError("Master did not return worker_id")
        return str(worker_id)

    def _next_task(self) -> TaskResponse | None:
        if not self.worker_id:
            raise RuntimeError("Worker not registered")
        query = urllib.parse.urlencode({"worker_id": self.worker_id})
        url = f"{self.master_url}/next_task?{query}"
        try:
            status, payload = _get_json(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 204:
                return None
            raise
        if status == 204 or payload is None:
            return None
        return _parse_task_response(payload)

    def _process_task(self, task: TaskResponse) -> TaskResult:
        request_payload = _model_dump(task.request)
        request_config = RequestConfig.from_dict(request_payload)
        proxy_selector = ProxySelector(request_config.proxies)
        fetcher = CloudscraperFetcher(proxy_selector)

        result = fetcher.fetch(task.url_normalized, request_config)
        parsed = None
        final_url = result.final_url
        render_error: str | None = None
        rendered_html: str | None = None
        annotations = None

        if result.error is None and _is_parsable(result.content_type):
            if task.rendering.enabled:
                render_config = RenderingConfig.from_dict(_model_dump(task.rendering))
                render_result = render_html(
                    task.url_normalized,
                    render_config,
                    result.proxy_used,
                )
                if render_result.error:
                    render_error = render_result.error
                if render_result.html:
                    rendered_html = render_result.html
                    if render_result.final_url:
                        final_url = render_result.final_url
            html_source = rendered_html or result.body.decode("utf-8", errors="replace")
            parsed = parse_html(
                html_source,
                extract_links=task.parsing.extract_links,
                max_links=task.parsing.max_links_per_page,
                extract_text=task.parsing.extract_text,
            )
        if render_error:
            logger.warning("Render failed for %s: %s", task.url_normalized, render_error)

        outlinks = parsed.links if parsed and task.parsing.extract_links else []
        text = parsed.text if parsed and task.parsing.extract_text else None
        sha = content_hash(result.body) if result.body else None
        body_b64 = base64.b64encode(result.body).decode("ascii") if result.body else None

        hook_config = HookConfig.from_dict(_model_dump(task.hooks))
        if should_run_hook(hook_config, distributed=True, role="worker"):
            try:
                hook_runner = HookRunner.from_config(hook_config, workspace=self.workspace)
                if hook_runner:
                    context = HookContext(
                        workspace=self.workspace,
                        source_id=task.source_id,
                        page_id=task.page_id,
                        url_original=task.url_original,
                        url_normalized=task.url_normalized,
                        final_url=final_url,
                        fetched_at=_utc_now(),
                        status_code=result.status_code,
                        content_type=result.content_type,
                        content_length=result.content_length,
                        headers=result.headers,
                        body=result.body,
                        text=text,
                        title=parsed.title if parsed else None,
                        h1=parsed.h1 if parsed else None,
                        word_count=parsed.word_count if parsed else None,
                        outlinks=outlinks or None,
                        proxy_used=result.proxy_used,
                    )
                    hook_result = hook_runner.run(context)
                    annotations = hook_result.annotations
            except Exception as exc:  # pragma: no cover - hook behavior
                logger.warning("Hook failed for %s: %s", task.url_normalized, exc)

        return TaskResult(
            task_id=task.task_id,
            page_id=task.page_id,
            url_original=task.url_original,
            url_normalized=task.url_normalized,
            final_url=final_url,
            status_code=result.status_code,
            headers=result.headers,
            body_b64=body_b64,
            error=result.error,
            content_type=result.content_type,
            content_length=result.content_length,
            sha256=sha,
            title=parsed.title if parsed else None,
            h1=parsed.h1 if parsed else None,
            word_count=parsed.word_count if parsed else None,
            text=text,
            outlinks=outlinks,
            proxy_used=result.proxy_used,
            annotations=annotations,
        )

    def _post_result(self, result: TaskResult) -> None:
        url = f"{self.master_url}/task_result"
        _post_json(url, _task_result_dict(result))


def _is_parsable(content_type: str | None) -> bool:
    if not content_type:
        return False
    lower_type = content_type.lower()
    return "html" in lower_type or lower_type.startswith("text/")


def _get_json(url: str) -> tuple[int, dict[str, object] | None]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request) as response:
        status = response.status
        if status == 204:
            return status, None
        body = response.read()
        payload = json.loads(body.decode("utf-8")) if body else None
        return status, payload


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        body = response.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))


def _parse_task_response(payload: dict[str, object]) -> TaskResponse:
    if hasattr(TaskResponse, "model_validate"):
        return TaskResponse.model_validate(payload)
    return TaskResponse.parse_obj(payload)


def _task_result_dict(result: TaskResult) -> dict[str, object]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result.dict()


def _model_dump(model) -> dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
