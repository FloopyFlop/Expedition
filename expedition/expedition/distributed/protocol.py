from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RegisterWorkerResponse(BaseModel):
    worker_id: str


class RequestPayload(BaseModel):
    timeout_seconds: int
    max_retries: int
    retry_backoff_seconds: float
    user_agent: str
    headers: dict[str, str]
    proxies: dict[str, Any]


class ParsingPayload(BaseModel):
    extract_text: bool
    extract_links: bool
    max_links_per_page: int | None


class HookPayload(BaseModel):
    enabled: bool
    script_path: str | None
    callable: str | None
    function: str
    run_on: str


class RenderingPayload(BaseModel):
    enabled: bool
    provider: str
    browser: str
    headless: bool
    timeout_seconds: int
    wait_until: str


class TaskResponse(BaseModel):
    task_id: str
    page_id: str
    url_original: str
    url_normalized: str
    depth: int
    parent_page_id: str | None
    discovered_at: str
    request: RequestPayload
    parsing: ParsingPayload
    hooks: HookPayload
    rendering: RenderingPayload


class TaskResult(BaseModel):
    task_id: str
    page_id: str
    url_original: str
    url_normalized: str
    final_url: str | None = None
    status_code: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body_b64: str | None = None
    error: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    sha256: str | None = None
    title: str | None = None
    h1: str | None = None
    word_count: int | None = None
    text: str | None = None
    outlinks: list[str] = Field(default_factory=list)
    proxy_used: str | None = None
    annotations: dict[str, Any] | None = None
