## Cron Job for Weekly Database Sync
0 0 * * 0 /absolute/path/to/venv/bin/python /absolute/path/to/db_sync.py >> /absolute/path/to/sync.log 2>&1

## Data Ingestion Pipeline
```
┌──────────────────────────────────────────────────────────────────────────┐
│                          External Data Sources                           │
│                                (TMDB API)                                │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                          HTTP Requests / REST APIs
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  Movie Data Ingestion Pipeline (db_sync.py)              │
├──────────────────────────────────────────────────────────────────────────┤
│  1. Fetch Trending Movies & IMDb Ratings                                 │
│  2. Fetch UK Streaming Provider Availability (Region: GB)                │
│  3. Data Cleaning, Genre Normalization & Deduplication                   │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                        SQLite Upserts (Atomic Transactions)
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      Local Database (movies.db)                          │
├────────────────────────────────────────────────┬─────────────────────────┤
│  movies Table                                  │ movie_providers Table   │
│  - id (PRIMARY KEY)                            │ - movie_id (FOREIGN KEY)│
│  - title                                       │ - platform              │
│  - imdb_score                                  │ - region ('GB')         │
│  - release_date                                │                         │
│  - genres                                      │                         │
└────────────────────────────────────┬───────────┴─────────────────────────┘
                                     │
                          SQLite Queries (Read-Only)
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                  Unified Server (unified_server.py)                      │
│            Serves Tool Calls to Open WebUI & Claude Desktop              │
└──────────────────────────────────────────────────────────────────────────┘
```


## Architecture Diagram Claude
```
┌─────────────────────────────────────────────────────────┐
│                   Claude Desktop App                    │
│                 Model: Claude Sonnet 5                  │
└───────────────────────────┬─────────────────────────────┘
│
Direct Local SSE (http://localhost:8000/sse)
or Stdio Transport
│
▼
┌─────────────────────────────────────────────────────────┐
│                 Unified Python Server                   │
│      (FastAPI REST + MCP v2 SSE Transport on :8000)     │
├───────────────────────────┬─────────────────────────────┤
│  REST: /openapi.json      │  MCP SSE: /sse              │
│  GET:  /search_trending...│  POST:    /messages/        │
└───────────────────────────┬─────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────┐
│                     SQLite Database                     │
│                       (movies.db)                       │
└───────────────────────────┴─────────────────────────────┘
```

## Ollama Gemma4:e2b Model Architecture
```
┌─────────────────────────────────────────────────────────┐
│                   Open WebUI (Docker)                   │
│           Models: Gemma4:e2b           │
└───────────────────────────┬─────────────────────────────┘
│
http://host.docker.internal:8000
│
▼
┌─────────────────────────────────────────────────────────┐
│                 Unified Python Server                   │
│      (FastAPI REST + MCP v2 SSE Transport on :8000)     │
├───────────────────────────┬─────────────────────────────┤
│  REST: /openapi.json      │  MCP SSE: /sse              │
│  GET:  /search_trending...│  POST:    /messages/        │
└───────────────────────────┬─────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────┐
│                     SQLite Database                     │
│                       (movies.db)                       │
└───────────────────────────┴─────────────────────────────┘
```