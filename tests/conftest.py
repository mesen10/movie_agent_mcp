import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SCHEMA = """
CREATE TABLE movies (
    id INTEGER PRIMARY KEY,
    title TEXT,
    imdb_score REAL,
    release_date TEXT,
    genres TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE movie_providers (
    movie_id INTEGER,
    platform TEXT,
    region TEXT,
    PRIMARY KEY (movie_id, platform, region)
);
"""


@pytest.fixture
def make_db(tmp_path):
    """Create a snapshot DB with the production schema and return its path."""

    def _make(movies=(), providers=()):
        path = tmp_path / "movies.db"
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO movies (id, title, imdb_score, release_date, genres) VALUES (?, ?, ?, ?, ?)",
            movies,
        )
        conn.executemany(
            "INSERT INTO movie_providers (movie_id, platform, region) VALUES (?, ?, ?)",
            providers,
        )
        conn.commit()
        conn.close()
        return str(path)

    return _make
