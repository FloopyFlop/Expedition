from __future__ import annotations

import posixpath
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


DEFAULT_DROP_PREFIXES = ["utm_", "fbclid", "gclid"]


def normalize_url(
    url: str,
    base_url: str | None = None,
    drop_query_param_prefixes: Iterable[str] | None = None,
) -> str:
    drop_prefixes = list(drop_query_param_prefixes or DEFAULT_DROP_PREFIXES)
    resolved = urljoin(base_url, url) if base_url else url
    split = urlsplit(resolved)

    scheme = split.scheme.lower()
    hostname = split.hostname.lower() if split.hostname else ""
    port = split.port

    userinfo = ""
    if split.username:
        userinfo = split.username
        if split.password:
            userinfo += f":{split.password}"
        userinfo += "@"

    netloc = hostname
    if port is not None and not _is_default_port(scheme, port):
        netloc = f"{hostname}:{port}"
    if userinfo:
        netloc = f"{userinfo}{netloc}"

    path = _normalize_path(split.path)

    query_pairs = []
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        if _is_tracking_param(key, drop_prefixes):
            continue
        query_pairs.append((key, value))
    query_pairs.sort(key=lambda pair: (pair[0], pair[1]))
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = posixpath.normpath(path)
    if normalized == ".":
        normalized = "/"
    if path.endswith("/") and normalized != "/":
        normalized += "/"
    return normalized


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _is_tracking_param(param_name: str, prefixes: list[str]) -> bool:
    lower_name = param_name.lower()
    return any(lower_name.startswith(prefix.lower()) for prefix in prefixes)
