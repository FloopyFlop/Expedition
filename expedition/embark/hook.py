from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from expedition.hooks import HookContext, HookResult

from .config import EmbarkConfig
from .db import load_db, save_db, upsert_drone
from .ollama import extract_drone_record

logger = logging.getLogger(__name__)


def process_page(context: HookContext) -> HookResult:
    config = EmbarkConfig.load(context.workspace)
    if not config.enabled:
        return HookResult(annotations={"embark": {"skipped": "disabled"}})

    text = context.text or ""
    if not text.strip():
        return HookResult(annotations={"embark": {"skipped": "no_text"}})

    record = extract_drone_record(
        text=text,
        title=context.title,
        url=context.final_url or context.url_normalized,
        config=config,
    )
    if not record:
        return HookResult(annotations={"embark": {"skipped": "no_record"}})

    record.setdefault("source_url", context.final_url or context.url_normalized)
    db_path = config.db_path(context.workspace)
    db = load_db(db_path)
    merged = upsert_drone(db, record)
    if merged:
        save_db(db_path, db)

    payload: dict[str, Any] = {
        "record": record,
        "record_key": merged.key if merged else None,
        "model": config.ollama_model,
        "extracted_at": _utc_now(),
    }
    return HookResult(annotations={"embark": payload})


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
