from __future__ import annotations

import base64
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .config import load_config
from .storage.factory import create_backend


def create_app(workspace: Path) -> FastAPI:
    config = load_config(workspace / "config.json")
    backend = create_backend(workspace, config)
    backend.ensure_workspace()

    app = FastAPI(title="Expedition Archive API")

    @app.get("/pages/{page_id}")
    def get_page(page_id: str, include_body: bool = False):
        metadata = backend.archive.read_metadata(page_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Page not found")

        request = backend.archive.read_request(page_id)
        response = backend.archive.read_response_headers(page_id)
        body_path = backend.archive.body_path(page_id)

        payload = {
            "metadata": metadata,
            "request": request,
            "response": response,
            "body_path": str(body_path) if body_path else None,
        }

        if include_body and body_path and body_path.exists():
            payload["body_b64"] = base64.b64encode(body_path.read_bytes()).decode("ascii")

        return payload

    @app.get("/pages/{page_id}/body")
    def get_body(page_id: str):
        metadata = backend.archive.read_metadata(page_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Page not found")
        body_path = backend.archive.body_path(page_id)
        if not body_path or not body_path.exists():
            raise HTTPException(status_code=404, detail="Body not found")
        content_type = metadata.get("content_type") or "application/octet-stream"
        return FileResponse(body_path, media_type=content_type, filename=body_path.name)

    @app.get("/sitemap")
    def get_sitemap(
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        source_id: str | None = None,
    ):
        if not source_id:
            entries = list(backend.sitemap.iter_entries(offset=offset, limit=limit))
            return {
                "items": entries,
                "offset": offset,
                "limit": limit,
                "next_offset": offset + len(entries),
            }

        filtered: list[dict] = []
        seen = 0
        for entry in backend.sitemap.iter_entries(offset=0, limit=None):
            if entry.get("source_id") != source_id:
                continue
            if seen < offset:
                seen += 1
                continue
            if len(filtered) >= limit:
                break
            filtered.append(entry)
            seen += 1
        return {
            "items": filtered,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + len(filtered),
        }

    @app.get("/sources")
    def get_sources():
        job_state = backend.job_state.load()
        return {
            "sources": [asdict(source) for source in config.sources],
            "source_status": job_state.source_status,
        }

    return app
