# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

UK Trending Movie Agent MCP server: exposes a local SQLite cache of TMDB trending-movie data over both a FastAPI REST API and an MCP v2 SSE server, on a single port (8000). Consumed by Claude Desktop (native MCP) and Open WebUI/Docker (REST + OpenAPI schema).

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

- **`db_sync.py`**: Standalone ingestion script, run separately (manually or via cron), not imported by the server. Wipes and repopulates `movies` and `movie_providers` tables each run (full snapshot replace, not incremental) by pulling ~500 trending movies from TMDB plus per-movie watch-provider availability for the configured region. Loads config via `python-dotenv` — `load_dotenv()` reads `.env` (not `local.env`; `local.env` is gitignored and not wired into any loader currently).
- **`unified_server.py`**: The actual entrypoint per `readme.md` and the Claude Desktop config. One FastAPI `app` mounts both the REST routes (`/search_trending_movies`, `/list_available_platforms`, `/get_subscription_pricing`) and an MCP `MCPServer` instance whose tools (`*_mcp` suffixed) wrap the same underlying `db_*` query functions — REST and MCP are two transports over identical business logic, defined once in this file. MCP SSE is hand-wired over FastAPI (`/sse` GET + `/messages/` POST via `SseServerTransport`), not via the MCP SDK's own ASGI mount. `openapi.json` is regenerated to disk on every startup (FastAPI `lifespan`).
- **Database** (`movies.db`, gitignored, rebuilt by `db_sync.py`): `movies` (id, title, imdb_score, release_date, genres as comma-joined string) and `movie_providers` (movie_id, platform, region — composite PK), joined via `LEFT JOIN` so movies with no streaming availability still return with a fallback string.
- Region/currency are UK-only by convention (`DEFAULT_REGION=GB`), and `get_subscription_pricing` returns a hardcoded GBP price table rather than querying TMDB or the DB.
- Port 8000 is hardcoded in `unified_server.py`.

## Client integration

Claude Desktop launches `unified_server.py` directly via its configured Python interpreter (see `readme.md` for the `claude_desktop_config.json` snippet) — it does not connect over HTTP/SSE in that mode. Open WebUI connects over HTTP to `/sse` and the REST routes via `host.docker.internal:8000`.
