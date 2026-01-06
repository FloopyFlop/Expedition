from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import cloudscraper

from .config import ProxyConfig, RequestConfig


@dataclass
class FetchResult:
    url: str
    final_url: str | None
    status_code: int | None
    headers: dict[str, str]
    body: bytes
    error: str | None
    elapsed_seconds: float | None
    content_type: str | None
    content_length: int | None
    proxy_used: str | None


class ProxySelector:
    def __init__(self, config: ProxyConfig) -> None:
        self._config = config
        self._index = 0

    def next_proxy(self) -> tuple[dict[str, str] | None, str | None]:
        if not self._config.enabled:
            return None, None

        if self._config.rotate and self._config.pool:
            proxy_url = self._config.pool[self._index % len(self._config.pool)]
            self._index += 1
            return {"http": proxy_url, "https": proxy_url}, proxy_url

        if self._config.pool and not self._config.rotate:
            proxy_url = self._config.pool[0]
            return {"http": proxy_url, "https": proxy_url}, proxy_url

        proxies: dict[str, str] = {}
        http_proxy = self._config.http or self._config.https
        https_proxy = self._config.https or self._config.http
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        used = https_proxy or http_proxy
        return proxies or None, used


class CloudscraperFetcher:
    def __init__(self, proxy_selector: ProxySelector | None = None) -> None:
        self._scraper = cloudscraper.create_scraper()
        self._proxy_selector = proxy_selector

    def fetch(self, url: str, request_config: RequestConfig) -> FetchResult:
        headers = dict(request_config.headers)
        if request_config.user_agent:
            headers["User-Agent"] = request_config.user_agent

        proxy_selector = self._proxy_selector or ProxySelector(request_config.proxies)
        proxies, proxy_used = proxy_selector.next_proxy()

        error: str | None = None
        response_headers: dict[str, str] = {}
        body = b""
        status_code: int | None = None
        final_url: str | None = None
        elapsed_seconds: float | None = None

        for attempt in range(request_config.max_retries + 1):
            start = time.monotonic()
            try:
                response = self._scraper.get(
                    url,
                    timeout=request_config.timeout_seconds,
                    headers=headers,
                    proxies=proxies,
                    allow_redirects=True,
                )
                elapsed_seconds = time.monotonic() - start
                status_code = response.status_code
                final_url = response.url
                response_headers = {str(k): str(v) for k, v in response.headers.items()}
                body = response.content or b""
                error = None
                break
            except Exception as exc:  # pragma: no cover - network variations
                elapsed_seconds = time.monotonic() - start
                error = str(exc)
                if attempt < request_config.max_retries:
                    backoff = request_config.retry_backoff_seconds * (attempt + 1)
                    if backoff > 0:
                        time.sleep(backoff)
                else:
                    break

        content_type = response_headers.get("Content-Type")
        content_length = len(body) if body else None

        return FetchResult(
            url=url,
            final_url=final_url,
            status_code=status_code,
            headers=response_headers,
            body=body,
            error=error,
            elapsed_seconds=elapsed_seconds,
            content_type=content_type,
            content_length=content_length,
            proxy_used=proxy_used,
        )
