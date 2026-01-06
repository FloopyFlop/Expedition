from __future__ import annotations

import hashlib


def url_fingerprint(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
