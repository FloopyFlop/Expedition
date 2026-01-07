# Expedition

Universal Web Scraping Library

Expedition is a local-first crawler + archiver that stores all state and outputs inside a single workspace directory. Jobs are resumable, pausable, and cancelable, and the crawl frontier is deduplicated with URL normalization.

## What it is

- Readable, configurable crawler for BFS/DFS traversal
- Local-only storage: config, job state, sitemap, archive, and logs live under one workspace directory
- CloudScraper-based fetching (no browser automation)
- HTML parsing for titles, outlinks, and optional text extraction
- Resume or move a workspace anywhere without losing state

## Quickstart (uv)

Minimal local crawl:

```bash
uv sync --dev
uv run expedition init --workspace ./workspace --seed-url https://example.com --max-depth 1
uv run expedition run --workspace ./workspace
```

Optional: serve the archive API:

```bash
uv run expedition serve --workspace ./workspace --port 8000
```

Optional: distributed mode (master + worker):

```bash
# enable distributed mode in workspace/config.json
uv run expedition resume --workspace ./workspace
uv run expedition master --workspace ./workspace --port 8001
uv run expedition worker --workspace ./worker --master http://127.0.0.1:8001
```

List mode (no link discovery):

```bash
# urls.txt contains one URL per line
uv run expedition init --workspace ./workspace --mode list --input-urls-file urls.txt
uv run expedition run --workspace ./workspace
```

Optional: browser rendering (Playwright):

```bash
uv sync --extra render
uv run python -m playwright install chromium
```

Then set in `config.json`:

```json
{
  "rendering": { "enabled": true, "provider": "playwright" }
}
```

## Proxying

Add a proxy in `config.json` (credentials will be redacted in archives):

```json
{
  "request": {
    "proxies": {
      "http": "http://user:pass@host:port",
      "https": "http://user:pass@host:port",
      "rotate": false,
      "pool": []
    }
  }
}
```

## Multi-source archives

You can crawl multiple roots and URL lists into one workspace and track each source separately.

```json
{
  "sources": [
    { "source_id": "agency-root", "mode": "crawl", "seed_url": "https://example.gov", "max_depth": 2 },
    { "source_id": "legacy-list", "mode": "list", "input_urls_file": "urls.txt" }
  ]
}
```

Check per-source progress:

```bash
uv run expedition sources --workspace ./workspace
```

## Hooks (optional)

Run a per-page hook script or callable:

```bash
uv run expedition init --workspace ./workspace --seed-url https://example.com \\
  --hook-script ./hook.py --hook-function process_page
```

## Embark demo

Embark is a standalone drone-extraction app built on Expedition. See `DEVELOPER_DOCS.md` for full usage.

If you want both tests + rendering in one environment:

```bash
uv sync --extra dev --extra render
uv run python -m playwright install chromium
```

## Workspace layout

Expedition keeps everything under the workspace folder:

```
workspace/
  config.json
  job_state.json
  sitemap.jsonl
  archive/
    pages/<page_id>/
      response_body.html
      response_headers.json
      request.json
      metadata.json
      text.txt
  logs/expedition.log
  logs/events.jsonl
```

## Notes

- `obey_robots_txt` is in the config but not implemented in the MVP.
- All caches and logs live inside the workspace directory.
- Proxies auto-enable when `request.proxies` includes `http`, `https`, or `pool`.

## Developer docs

For programmatic/library usage, see `DEVELOPER_DOCS.md`.

## Distributed config

Add to `config.json` to enable the master/worker flow:

```json
{
  "distributed": {
    "enabled": true,
    "master_url": "http://127.0.0.1:8001",
    "worker_poll_interval_seconds": 2.0
  }
}
```

## Archive API (local)

- `GET /pages/{page_id}` returns metadata, request/response headers, and a body path.
- `GET /pages/{page_id}/body` returns the raw body bytes.
- `GET /sitemap?offset=0&limit=100` returns sitemap entries.

## Tests

```bash
uv sync --extra dev
uv run pytest
```

## License

MIT. See `LICENSE`.
