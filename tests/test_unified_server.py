import unified_server as srv


def _point_at(monkeypatch, path):
    monkeypatch.setattr(srv, "DB_PATH", path)


MOVIES = [
    (1, "Alien", 8.1, "1979-05-25", "horror,scifi"),
    (2, "Heat", 8.3, "1995-12-15", "crime,thriller"),
    (3, "Paddington", 7.4, "2014-11-28", "family,comedy"),
    (4, "Bad Film", 4.0, "2020-01-01", "horror"),
]
PROVIDERS = [
    (1, "Netflix", "GB"),
    (1, "Disney Plus", "GB"),
    (2, "Netflix", "GB"),
    (3, "Amazon Prime Video", "GB"),
]


def test_search_filters_by_min_rating(monkeypatch, make_db):
    _point_at(monkeypatch, make_db(MOVIES, PROVIDERS))
    ids = [m["id"] for m in srv.db_search_trending_movies(min_rating=7.5)]
    assert ids == [2, 1]  # ordered by score desc, Bad Film excluded


def test_search_filters_by_genre_case_insensitively(monkeypatch, make_db):
    _point_at(monkeypatch, make_db(MOVIES, PROVIDERS))
    titles = [m["title"] for m in srv.db_search_trending_movies(genre="HORROR", min_rating=0)]
    assert titles == ["Alien", "Bad Film"]  # both horror, ordered by score desc
    assert "Heat" not in titles


def test_search_returns_fallback_when_no_platforms(monkeypatch, make_db):
    _point_at(monkeypatch, make_db([(9, "Lonely", 9.0, "2001-01-01", "drama")], []))
    [movie] = srv.db_search_trending_movies(min_rating=0)
    assert movie["available_platforms"] == ["Not available on tracked subscription platforms"]
    assert movie["genres"] == ["drama"]


def test_platform_filter_keeps_all_platforms_of_matching_movie(monkeypatch, make_db):
    # Alien is on Netflix AND Disney Plus; filtering by Netflix must still list both.
    _point_at(monkeypatch, make_db(MOVIES, PROVIDERS))
    results = {m["title"]: m for m in srv.db_search_trending_movies(platform="netflix", min_rating=0)}
    assert set(results) == {"Alien", "Heat"}
    assert sorted(results["Alien"]["available_platforms"]) == ["Disney Plus", "Netflix"]


def test_list_platforms_is_sorted_and_distinct(monkeypatch, make_db):
    _point_at(monkeypatch, make_db(MOVIES, PROVIDERS))
    assert srv.db_list_available_platforms() == ["Amazon Prime Video", "Disney Plus", "Netflix"]


def test_missing_db_returns_error_not_crash(monkeypatch, tmp_path):
    _point_at(monkeypatch, str(tmp_path / "nope.db"))
    assert "error" in srv.db_search_trending_movies()[0]
    assert srv.db_list_available_platforms() == []


def test_rest_search_endpoint(monkeypatch, make_db):
    from fastapi.testclient import TestClient

    _point_at(monkeypatch, make_db(MOVIES, PROVIDERS))
    client = TestClient(srv.app)
    resp = client.get("/search_trending_movies", params={"genre": "horror", "min_rating": 7.0})
    assert resp.status_code == 200
    assert [m["title"] for m in resp.json()] == ["Alien"]


def test_rest_pricing_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    body = TestClient(srv.app).get("/get_subscription_pricing").json()
    assert body["currency"] == "£"
    assert "Netflix" in body


def test_cors_does_not_combine_wildcard_origin_with_credentials():
    # Browsers reject `Access-Control-Allow-Origin: *` together with credentials.
    cors = next(m for m in srv.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert not (cors.kwargs.get("allow_origins") == ["*"] and cors.kwargs.get("allow_credentials"))
