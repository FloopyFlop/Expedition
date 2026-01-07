# Embark

Embark is a standalone drone data collection app built on Expedition. It crawls pages, extracts drone specs with Ollama, and merges them into a local JSON database inside the workspace.

## Quickstart

Prereqs:

- `ollama` installed and running (local API at `http://localhost:11434`)
- Expedition repo with `uv` set up

Start Ollama (if not already running):

```bash
ollama serve
```

### Demo (local site)

Run the bundled demo site:

```bash
python3 -m http.server 8124 --bind 127.0.0.1 --directory expedition/embark/demo_site
```

Initialize and run Embark:

```bash
uv run embark init --workspace ./embark_workspace \
  --seed-url http://127.0.0.1:8124/index.html \
  --max-depth 1 --max-pages 10 \
  --ollama-model llama3.2:latest

uv run embark run --workspace ./embark_workspace
```

Results:

- Drone database: `embark_workspace/embark/drone_db.json`
- Page annotations: `embark_workspace/archive/pages/<page_id>/metadata.json`

## Configuration

Embark writes a local config file:

- `embark_workspace/embark_config.json`

You can change:

- `ollama_url`
- `ollama_model`
- `timeout_seconds`
- `max_input_chars`
- `db_filename`

## Notes

- Embark uses Expedition hooks (`embark.hook:process_page`) to extract data per page.
- If Ollama is not running, pages still crawl but annotations will show `skipped`.
