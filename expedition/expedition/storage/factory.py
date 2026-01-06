from __future__ import annotations

from pathlib import Path

from ..config import ExpeditionConfig
from .interfaces import StorageBackend
from .local_json import LocalJsonBackend
from .stubs import RemoteBackendStub


def create_backend(workspace: Path, config: ExpeditionConfig) -> StorageBackend:
    if config.storage.type == "local_json":
        return LocalJsonBackend(workspace, config)
    if config.storage.type in {"remote_stub", "firebase"}:
        return RemoteBackendStub(workspace, config)
    raise ValueError(f"Unknown storage type: {config.storage.type}")
