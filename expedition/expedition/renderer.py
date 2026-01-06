from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .config import RenderingConfig


@dataclass
class RenderResult:
    html: str | None
    final_url: str | None
    error: str | None


def render_html(
    url: str,
    config: RenderingConfig,
    proxy_url: str | None,
) -> RenderResult:
    if not config.enabled:
        return RenderResult(html=None, final_url=None, error=None)

    if config.provider != "playwright":
        return RenderResult(
            html=None,
            final_url=None,
            error=f"Unsupported renderer: {config.provider}",
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dependency
        return RenderResult(
            html=None,
            final_url=None,
            error=f"Playwright not available: {exc}",
        )

    proxy_settings = _playwright_proxy(proxy_url)

    try:
        with sync_playwright() as playwright:
            browser_type = _browser_type(playwright, config.browser)
            browser = browser_type.launch(headless=config.headless, proxy=proxy_settings)
            try:
                context = browser.new_context()
                page = context.new_page()
                response = page.goto(
                    url,
                    timeout=config.timeout_seconds * 1000,
                    wait_until=config.wait_until,
                )
                html = page.content()
                final_url = page.url
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - optional runtime behavior
        return RenderResult(html=None, final_url=None, error=str(exc))

    return RenderResult(html=html, final_url=final_url, error=None)


def _browser_type(playwright: Any, browser_name: str):
    name = (browser_name or "chromium").lower()
    if name == "firefox":
        return playwright.firefox
    if name == "webkit":
        return playwright.webkit
    return playwright.chromium


def _playwright_proxy(proxy_url: str | None) -> dict[str, str] | None:
    if not proxy_url:
        return None
    split = urlsplit(proxy_url)
    if not split.scheme or not split.hostname:
        return None

    server = f"{split.scheme}://{split.hostname}"
    if split.port:
        server = f"{server}:{split.port}"

    payload = {"server": server}
    if split.username:
        payload["username"] = split.username
    if split.password:
        payload["password"] = split.password
    return payload
