# Expedition Developer Docs

This document is the long-form guide for using Expedition as a Python library. It focuses on programmatic orchestration, test harnesses, and embedding Expedition into your own tools.

## Install and setup (uv)

Inside the Expedition repo:

```bash
uv sync --dev
```

If you need rendering:

```bash
uv sync --extra render
uv run python -m playwright install chromium
```

If you want tests + rendering together:

```bash
uv sync --extra dev --extra render
uv run python -m playwright install chromium
```

From another project, add Expedition as a path dependency:

```bash
uv add --editable /path/to/Expedition
```

## Library entry points

Expedition now exposes a small programmatic API:

- `ExpeditionConfig`: configure the run.
- `init_workspace(...)`: create a workspace and write config + job state.
- `run_workspace(...)`: run a job in a workspace (uses job state + config on disk).
- `pause_workspace(...)`, `resume_workspace(...)`, `cancel_workspace(...)`.
- `get_status(...)`: summary of job state.
- `load_workspace(...)`: returns `(config, backend, job_state)` for advanced use.

These are imported from the top-level package:

```python
from expedition import (
    ExpeditionConfig,
    init_workspace,
    run_workspace,
    pause_workspace,
    resume_workspace,
    cancel_workspace,
    get_status,
    load_workspace,
)
```

## Single-file orchestration (recommended starting point)

This is a minimal, self-contained runner in one Python file:

```python
from pathlib import Path

from expedition import ExpeditionConfig, init_workspace, run_workspace, get_status

workspace = Path("./workspace_dev")

config = ExpeditionConfig(
    mode="crawl",
    seed_url="https://example.com",
    traversal="bfs",
    max_depth=2,
    max_pages=25,
)
config.parsing.extract_text = True
config.concurrency.max_workers = 4

if not (workspace / "config.json").exists():
    init_workspace(workspace, config)

run_workspace(workspace)
print(get_status(workspace))
```

This pattern is deliberate:

- The workspace contains all state and can be moved or resumed later.
- `run_workspace` always reads config and job state from disk.
- Use `max_pages` to cap work in small test runs.

## Workspace lifecycle

### Initialize

```python
init_workspace(Path("./workspace"), config)
```

### Run

```python
run_workspace(Path("./workspace"))
```

### Pause, resume, cancel

```python
pause_workspace(Path("./workspace"))
resume_workspace(Path("./workspace"))  # resumes and runs by default
cancel_workspace(Path("./workspace"))
```

If you only want to flip state without running immediately:

```python
resume_workspace(Path("./workspace"), run=False)
```

## List mode (no link discovery)

In list mode, `input_urls_file` is resolved relative to the workspace if it is not absolute. Put the file inside the workspace.

```python
from pathlib import Path
from expedition import ExpeditionConfig, init_workspace, run_workspace

workspace = Path("./workspace_list")
workspace.mkdir(exist_ok=True)

urls_path = workspace / "urls.txt"
urls_path.write_text(
    "https://example.com\nhttps://example.com/about\n",
    encoding="utf-8",
)

config = ExpeditionConfig(
    mode="list",
    input_urls_file="urls.txt",
    max_depth=0,
    max_pages=10,
)

init_workspace(workspace, config)
run_workspace(workspace)
```

## Reading results programmatically

The simplest path is to read JSON/JSONL files directly:

```python
import json
from pathlib import Path

workspace = Path("./workspace_dev")

entries = []
for line in (workspace / "sitemap.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        entries.append(json.loads(line))
print(entries[:3])
```

For richer access, use the backend:

```python
from expedition.storage.local_json import LocalJsonBackend
from expedition.config import load_config

workspace = Path("./workspace_dev")
config = load_config(workspace / "config.json")
backend = LocalJsonBackend(workspace, config)

meta = backend.archive.read_metadata("00000001")
req = backend.archive.read_request("00000001")
headers = backend.archive.read_response_headers("00000001")
```

## Proxies

Set proxies in the config (credentials are redacted in archives):

```python
config.request.proxies.http = "http://user:pass@host:port"
config.request.proxies.https = "http://user:pass@host:port"
```

Pool/rotation is supported:

```python
config.request.proxies.rotate = True
config.request.proxies.pool = [
    "http://user:pass@host1:port",
    "http://user:pass@host2:port",
]
```

## Rendering (Playwright)

Rendering is optional and only runs when enabled:

```python
config.rendering.enabled = True
config.rendering.provider = "playwright"
config.rendering.browser = "chromium"
config.rendering.headless = True
```

Make sure Playwright is installed:

```bash
uv sync --extra render
uv run python -m playwright install chromium
```

## Distributed master/worker (programmatic)

### Master (FastAPI)

```python
from expedition.distributed.master import create_master_app
import uvicorn

app = create_master_app(Path("./workspace_dist"))
uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
```

### Worker (in-process thread)

`WorkerClient.run` accepts an optional `threading.Event` to stop the loop:

```python
import threading

from expedition.distributed.worker import WorkerClient

stop_event = threading.Event()
worker = WorkerClient(
    master_url="http://127.0.0.1:8001",
    workspace=Path("./worker_workspace"),
    poll_interval=0.5,
)
thread = threading.Thread(target=worker.run, args=(stop_event,), daemon=True)
thread.start()

# When you want to stop:
stop_event.set()
thread.join(timeout=5)
```

In production you may prefer separate processes and terminate workers when the job status becomes `completed`.

## Archive API (programmatic)

Expose the local archive API:

```python
from expedition.api import create_app
import uvicorn

app = create_app(Path("./workspace_dev"))
uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
```

Endpoints:

- `GET /pages/{page_id}`
- `GET /pages/{page_id}/body`
- `GET /sitemap?offset=0&limit=100`

## Machine-level smoke test (checklist + script)

This is a manual, high-coverage test you can run locally.

1) Create a local site:

```bash
mkdir -p ./smoke_site
printf '<html><body><a href="/a.html">A</a></body></html>' > ./smoke_site/index.html
printf '<html><body><a href="/b.html">B</a></body></html>' > ./smoke_site/a.html
printf '<html><body>Done</body></html>' > ./smoke_site/b.html
python3 -m http.server 8123 --bind 127.0.0.1 --directory ./smoke_site
```

2) Run a BFS crawl from a single Python file:

```python
from pathlib import Path
from expedition import ExpeditionConfig, init_workspace, run_workspace

workspace = Path("./workspace_smoke")
config = ExpeditionConfig(seed_url="http://127.0.0.1:8123/index.html", max_depth=2)
init_workspace(workspace, config)
run_workspace(workspace)
```

3) Check outputs:

- `workspace_smoke/sitemap.jsonl` has 3 entries.
- `workspace_smoke/archive/pages/<page_id>/` has body + headers + metadata.
- `workspace_smoke/logs/expedition.log` includes progress.

4) Optional: enable rendering and rerun with `rendering.enabled = True`.

5) Optional: enable list mode using a local `urls.txt` file.

6) Optional: run the archive API and query `/sitemap`.

## Troubleshooting

- Job ends immediately: check `job_state.json` status. If it is `paused`, call `resume_workspace`.
- List mode file not found: `input_urls_file` is resolved relative to the workspace.
- Proxy not applied: ensure `request.proxies.http/https` is set in config; it auto-enables.
- Rendering not working: run the Playwright install step and enable `config.rendering.enabled`.

## Notes on stability

- The workspace contract is stable: moving the workspace preserves the job.
- `rendering` and `distributed` are optional and can be disabled without affecting core crawling.
- All state is stored inside the workspace directory; no global files are required.
