from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from .config import EmbarkConfig

logger = logging.getLogger(__name__)


def extract_drone_record(
    *,
    text: str,
    title: str | None,
    url: str,
    config: EmbarkConfig,
) -> dict[str, Any] | None:
    prompt = _build_prompt(text=text, title=title, url=url, max_chars=config.max_input_chars)
    response = _ollama_generate(config, prompt)
    if response is None:
        return None
    payload = _extract_json(response)
    return payload


def _ollama_generate(config: EmbarkConfig, prompt: str) -> str | None:
    endpoint = f"{config.ollama_url.rstrip('/')}/api/generate"
    body = json.dumps(
        {
            "model": config.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("response")
    except urllib.error.URLError as exc:
        logger.warning("Ollama request failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected Ollama error: %s", exc)
        return None


def _build_prompt(*, text: str, title: str | None, url: str, max_chars: int) -> str:
    clipped = text[:max_chars]
    title_line = f"Title: {title}\n" if title else ""
    return (
        "You are extracting drone product information from a web page.\n"
        "Return ONLY a single JSON object. If no drone info is present, return {}.\n"
        "Required fields:\n"
        "- name (string)\n"
        "- manufacturer (string)\n"
        "- category (string)\n"
        "- weight_kg (number or null)\n"
        "- max_payload_kg (number or null)\n"
        "- flight_time_minutes (number or null)\n"
        "- range_km (number or null)\n"
        "- max_speed_kmh (number or null)\n"
        "- sensors (list of strings)\n"
        "- notes (string)\n"
        "- source_url (string)\n"
        "Use null for unknown numbers and [] for missing sensors.\n"
        f"{title_line}"
        f"URL: {url}\n"
        "CONTENT:\n"
        f"{clipped}\n"
    )


def _extract_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = raw[start : end + 1]
    try:
        payload = json.loads(candidate)
        if not isinstance(payload, dict):
            return None
        return payload
    except json.JSONDecodeError:
        return None
