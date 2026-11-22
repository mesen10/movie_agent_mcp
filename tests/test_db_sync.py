import os
import sqlite3

import pytest

import db_sync

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _fake_tmdb(monkeypatch, trending_pages, providers_by_id, trending_status=200):
    """Route requests.get to canned TMDB responses. trending_pages: {page: [movie, ...]}."""

    def fake_get(url, params=None, **kwargs):
        if url.endswith("/trending/movie/week"):
            page = params["page"]
            if trending_status != 200:
                return FakeResponse(trending_status)
            return FakeResponse(200, {"results": trending_pages.get(page, [])})
        if "/watch/providers" in url:
            movie_id = int(url.split("/movie/")[1].split("/")[0])
            return FakeResponse(200, {"results": providers_by_id.get(movie_id, {})})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(db_sync.requests, "get", fake_get)


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "movies.db")
    monkeypatch.setattr(db_sync, "DB_PATH", path)
    monkeypatch.setattr(db_sync, "TMDB_API_KEY", "test-key")
    monkeypatch.setattr(db_sync, "REGION", "GB")
    return path


def test_db_path_is_next_to_script_not_cwd():
    assert db_sync.DB_PATH == os.path.join(ROOT, "movies.db")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(db_sync, "TMDB_API_KEY", None)
    with pytest.raises(ValueError):
        db_sync.sync_movies()


def test_sync_stores_movies_genres_and_flatrate_providers(monkeypatch, db_path):
    trending = {
        1: [
            {"id": 10, "title": "Alien", "vote_average": 8.1, "release_date": "1979-05-25",
             "genre_ids": [27, 878, 99999]},  # unknown genre id must be dropped
            {"id": 11, "title": "Heat", "vote_average": 8.3, "release_date": "1995-12-15",
             "genre_ids": [80]},
            {"id": 10, "title": "Alien (dup)", "vote_average": 8.1, "release_date": "1979-05-25",
             "genre_ids": [27]},  # duplicate id across pages must be ignored
        ]
    }
    providers = {
        10: {"GB": {"flatrate": [{"provider_name": "Netflix"}, {"provider_name": " "}],
                    "rent": [{"provider_name": "Apple TV"}]}},  # rent is not subscription
        11: {"US": {"flatrate": [{"provider_name": "Hulu"}]}},  # other region ignored
    }
    _fake_tmdb(monkeypatch, trending, providers)

    db_sync.sync_movies()

    conn = sqlite3.connect(db_path)
    movies = conn.execute("SELECT id, title, genres FROM movies ORDER BY id").fetchall()
    provs = conn.execute("SELECT movie_id, platform, region FROM movie_providers ORDER BY movie_id").fetchall()
    conn.close()

    assert movies == [(10, "Alien", "horror,scifi"), (11, "Heat", "crime")]
    assert provs == [(10, "Netflix", "GB")]


def test_sync_replaces_previous_snapshot(monkeypatch, db_path):
    _fake_tmdb(monkeypatch, {1: [{"id": 1, "title": "Old", "vote_average": 5}]}, {})
    db_sync.sync_movies()
    _fake_tmdb(monkeypatch, {1: [{"id": 2, "title": "New", "vote_average": 6}]}, {})
    db_sync.sync_movies()

    conn = sqlite3.connect(db_path)
    titles = [r[0] for r in conn.execute("SELECT title FROM movies")]
    conn.close()
    assert titles == ["New"]


def test_failed_refresh_keeps_existing_snapshot(monkeypatch, db_path):
    # Regression: if TMDB is unavailable, the sync must not wipe the cached data.
    _fake_tmdb(monkeypatch, {1: [{"id": 1, "title": "Keep me", "vote_average": 7}]}, {})
    db_sync.sync_movies()

    _fake_tmdb(monkeypatch, {}, {}, trending_status=503)
    with pytest.raises(RuntimeError):
        db_sync.sync_movies()

    conn = sqlite3.connect(db_path)
    titles = [r[0] for r in conn.execute("SELECT title FROM movies")]
    conn.close()
    assert titles == ["Keep me"]
