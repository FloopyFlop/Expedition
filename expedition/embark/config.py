from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class EmbarkConfig:
    enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    timeout_seconds: int = 60
    max_input_chars: int = 8000
    db_filename: str = "embark/drone_db.json"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "EmbarkConfig":
        return EmbarkConfig(
            enabled=bool(data.get("enabled", True)),
            ollama_url=str(data.get("ollama_url", "http://localhost:11434")),
            ollama_model=str(data.get("ollama_model", "llama3")),
            timeout_seconds=int(data.get("timeout_seconds", 60)),
            max_input_chars=int(data.get("max_input_chars", 8000)),
            db_filename=str(data.get("db_filename", "embark/drone_db.json")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def load(workspace: Path) -> "EmbarkConfig":
        path = workspace / "embark_config.json"
        if not path.exists():
            return EmbarkConfig()
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return EmbarkConfig.from_dict(data)

    def save(self, workspace: Path) -> None:
        path = workspace / "embark_config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")

    def db_path(self, workspace: Path) -> Path:
        return workspace / self.db_filename
