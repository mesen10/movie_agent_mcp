import os
import json
import sqlite3
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.mcpserver import MCPServer
from mcp.server.sse import SseServerTransport
import uvicorn


def export_openapi_json(app: FastAPI):
    openapi_data = app.openapi()
    file_path = os.path.join(os.getcwd(), "openapi.json")
    with open(file_path, "w") as f:
        json.dump(openapi_data, f, indent=2)
    print(f"Generated openapi.json at: {file_path}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    export_openapi_json(app)
    yield

# 1. Initialize FastAPI Application
app = FastAPI(
    title="Movie Agent API",
    description="Unified REST and MCP server for local UK trending movie database",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.abspath("movies.db")

# 2. Shared Database Query Logic
def db_search_trending_movies(genre: Optional[str] = None, min_rating: float = 6.0, platform: Optional[str] = None, limit: int = 20) -> List[Dict]:
    if not os.path.exists(DB_PATH):
        return [{"error": "Database not initialized. Run db_sync.py first."}]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT DISTINCT m.id, m.title, m.imdb_score, m.release_date, m.genres,
               GROUP_CONCAT(p.platform, ', ') AS platforms
        FROM movies m
        LEFT JOIN movie_providers p ON m.id = p.movie_id
        WHERE m.imdb_score >= ?
    """
    params = [min_rating]

    if genre:
        query += " AND LOWER(m.genres) LIKE ?"
        params.append(f"%{genre.lower()}%")

    if platform:
        query += " AND LOWER(p.platform) LIKE ?"
        params.append(f"%{platform.lower()}%")

    query += " GROUP BY m.id ORDER BY m.imdb_score DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "title": row["title"],
            "imdb_score": row["imdb_score"],
            "release_date": row["release_date"],
            "genres": row["genres"].split(",") if row["genres"] else [],
            "available_platforms": row["platforms"].split(", ") if row["platforms"] else ["Not available on tracked subscription platforms"]
        })

    conn.close()
    return results

def db_list_available_platforms() -> List[str]:
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT platform FROM movie_providers WHERE region = 'GB' ORDER BY platform ASC")
    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows if row[0]]

def db_get_subscription_pricing(region: str = "GB") -> Dict[str, str]:
    return {
        "currency": "£",
        "Netflix": "£10.99 / mo",
        "Amazon Prime Video": "£8.99 / mo",
        "Disney Plus": "£7.99 / mo",
        "Apple TV Plus": "£8.99 / mo",
        "Paramount Plus": "£6.99 / mo",
        "Now (Sky Cinema)": "£9.99 / mo"
    }

# 3. FastAPI REST Routes
@app.get("/search_trending_movies", summary="Search Trending Movies")
def search_trending_movies(
    genre: Optional[str] = Query(None, description="Filter by genre ('action', 'comedy', 'drama', 'horror', 'scifi', 'thriller', etc.)"),
    min_rating: float = Query(6.0, description="Minimum IMDb score (default 6.0)"),
    platform: Optional[str] = Query(None, description="Streaming platform ('Netflix', 'Amazon Prime Video', 'Disney Plus', 'Apple TV Plus', etc.)"),
    limit: int = Query(20, description="Maximum records to return")
):
    return db_search_trending_movies(genre, min_rating, platform, limit)

@app.get("/list_available_platforms", summary="List Available Platforms")
def list_available_platforms():
    return db_list_available_platforms()

@app.get("/get_subscription_pricing", summary="Get Subscription Pricing")
def get_subscription_pricing(region: str = "GB"):
    return db_get_subscription_pricing(region)

# 4. MCP Server Setup & Mount
mcp = MCPServer("SQLite Fresh Movie Server")

@mcp.tool()
def search_trending_movies_mcp(genre: Optional[str] = None, min_rating: float = 6.0, platform: Optional[str] = None, limit: int = 20):
    return db_search_trending_movies(genre, min_rating, platform, limit)

@mcp.tool()
def list_available_platforms_mcp():
    return db_list_available_platforms()

@mcp.tool()
def get_subscription_pricing_mcp(region: str = "GB"):
    return db_get_subscription_pricing(region)

sse = SseServerTransport("/messages/")

@app.get("/sse")
async def handle_sse(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())

@app.post("/messages/")
async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)