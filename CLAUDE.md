# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

UK Trending Movie Agent MCP server: exposes a local SQLite cache of TMDB trending-movie data over both a FastAPI REST API and an MCP v2 SSE server, on a single port (8000), plus a stdio MCP transport for Claude Desktop. Consumed by Claude Desktop (native MCP, stdio) and Open WebUI/Docker (REST + OpenAPI schema).

## Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Populate/refresh the SQLite cache from TMDB (run before first use, and weekly via cron)
python db_sync.py

# Run the server (REST + MCP SSE on http://0.0.0.0:8000)
python unified_server.py

# Run as a stdio MCP server instead (no port bound — what Claude Desktop launches)
python unified_server.py --stdio

# Register/remove/check this server in Claude Desktop and Open WebUI
python setup_clients.py            # add to both (default)
python setup_clients.py status
python setup_clients.py remove
```

No test suite, linter, or formatter config exists in this repo.

### Manual verification

```bash
curl http://localhost:8000/openapi.json
curl "http://localhost:8000/search_trending_movies?genre=horror&min_rating=7.0"
curl http://localhost:8000/sse
```

## Architecture

**Pipeline:** `db_sync.py` (TMDB API → SQLite) → `movies.db` → `unified_server.py` (serves REST + MCP from the DB).

- **`db_sync.py`**: Standalone ingestion script, run separately (manually or via cron), not imported by the server. Wipes and repopulates `movies` and `movie_providers` tables each run (full snapshot replace, not incremental) by pulling ~500 trending movies from TMDB plus per-movie watch-provider availability for the configured region. Loads config via `python-dotenv` — `load_dotenv()` reads `.env`, which is tracked in git (keep real secrets out of it). `local.env` is gitignored and holds real secrets (TMDB key, `OPENWEBUI_API_KEY`); it's loaded only by `setup_clients.py`, not by `db_sync.py` or `unified_server.py`.
- **`unified_server.py`**: The actual entrypoint per `readme.md` and the Claude Desktop config. One FastAPI `app` mounts both the REST routes (`/search_trending_movies`, `/list_available_platforms`, `/get_subscription_pricing`) and an MCP `MCPServer` instance whose tools (`*_mcp` suffixed) wrap the same underlying `db_*` query functions — REST and MCP are two transports over identical business logic, defined once in this file. MCP SSE is hand-wired over FastAPI (`/sse` GET + `/messages/` POST via `SseServerTransport`), not via the MCP SDK's own ASGI mount. `openapi.json` is regenerated to disk on every startup (FastAPI `lifespan`), written next to the script (not relative to cwd). Run with `--stdio` to instead start `mcp.run_stdio_async()` and skip uvicorn/port binding entirely — this is what Claude Desktop launches, one subprocess per session, so concurrent sessions don't collide on port 8000.
- **`setup_clients.py`**: Registers/removes/checks this server as a client in Claude Desktop (writes `~/Library/Application Support/Claude/claude_desktop_config.json`, backing up the previous version to `.bak`) and in Open WebUI (calls its admin `/api/v1/configs/tool_servers` API). Not imported by the server; run standalone. Reads `OPENWEBUI_API_KEY` from `local.env` or the environment, or prompts for it interactively.
- **Database** (`movies.db`, gitignored, rebuilt by `db_sync.py`): `movies` (id, title, imdb_score, release_date, genres as comma-joined string) and `movie_providers` (movie_id, platform, region — composite PK), joined via `LEFT JOIN` so movies with no streaming availability still return with a fallback string.
- Region/currency are UK-only by convention (`DEFAULT_REGION=GB`), and `get_subscription_pricing` returns a hardcoded GBP price table rather than querying TMDB or the DB.
- Port 8000 is hardcoded in `unified_server.py` for the REST/SSE path; `--stdio` mode binds no port.

## Client integration

Claude Desktop launches `python unified_server.py --stdio` directly via its configured Python interpreter (see `readme.md`, or run `python setup_clients.py` to write the config automatically) — it talks MCP over stdio, not HTTP/SSE, in that mode. Open WebUI connects over HTTP to `/sse` and the REST routes via `host.docker.internal:8000`; `setup_clients.py` can register it there too via Open WebUI's admin API, given an `OPENWEBUI_API_KEY`.
