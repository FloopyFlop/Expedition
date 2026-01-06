from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class EventLogger:
    path: Path

    def log(self, event: str, payload: dict[str, Any] | None = None) -> None:
        record = {
            "timestamp": _utc_now(),
            "event": event,
        }
        if payload:
            record.update(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
