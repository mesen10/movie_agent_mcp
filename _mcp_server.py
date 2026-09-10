import os
import sqlite3
from typing import List, Dict, Optional
from mcp.server.mcpserver import MCPServer

# MCP 2.x MCPServer initialization
mcp = MCPServer("SQLite Fresh Movie Server")
DB_PATH = os.path.abspath("movies.db")


@mcp.tool()
def search_trending_movies(
        genre: Optional[str] = None,
        min_rating: float = 6.0,
        platform: Optional[str] = None,
        limit: int = 20
) -> List[Dict]:
    """
    Queries current trending movies from local SQLite cache.

    :param genre: Filter by genre ('action', 'comedy', 'drama', 'horror', 'romance', 'scifi', 'thriller', etc.)
    :param min_rating: Minimum IMDb score (default 6.0)
    :param platform: Streaming platform filter ('Netflix', 'Amazon Prime Video', 'Disney Plus', 'Apple TV Plus', etc.)
    :param limit: Maximum records to return
    """
    if not os.path.exists(DB_PATH):
        return [{"error": "Database not initialized. Run db_sync.py first."}]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
            SELECT DISTINCT m.id, \
                            m.title, \
                            m.imdb_score, \
                            m.release_date, \
                            m.genres,
                            GROUP_CONCAT(p.platform, ', ') AS platforms
            FROM movies m
                     LEFT JOIN movie_providers p ON m.id = p.movie_id
            WHERE m.imdb_score >= ? \
            """
    params = [min_rating]

    if genre:
        query += " AND m.genres LIKE ?"
        params.append(f"%{genre.lower()}%")

    if platform:
        query += " AND p.platform LIKE ?"
        params.append(f"%{platform}%")

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
            "available_platforms": row["platforms"].split(", ") if row["platforms"] else [
                "Not available on tracked subscription platforms"]
        })

    conn.close()
    return results


@mcp.tool()
def list_available_platforms() -> List[str]:
    """
    Returns a distinct list of all streaming platforms currently present in the database.
    """
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT platform FROM movie_providers WHERE region = 'GB' ORDER BY platform ASC")
    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows if row[0]]


@mcp.tool()
def get_subscription_pricing(region: str = "GB") -> Dict[str, str]:
    """
    Returns monthly subscription pricing in GBP (£) for major UK platforms.
    """
    return {
        "currency": "£",
        "Netflix": "£10.99 / mo",
        "Amazon Prime Video": "£8.99 / mo",
        "Disney Plus": "£7.99 / mo",
        "Apple TV Plus": "£8.99 / mo",
        "Paramount Plus": "£6.99 / mo",
        "Now (Sky Cinema)": "£9.99 / mo"
    }


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8000)