import os
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DB_PATH = os.path.abspath("movies.db")
REGION = os.getenv("DEFAULT_REGION", "GB")

GENRE_MAP = {
    28: "action", 12: "adventure", 16: "animation", 35: "comedy",
    80: "crime", 99: "documentary", 18: "drama", 10751: "family",
    14: "fantasy", 36: "history", 27: "horror", 10402: "music",
    9648: "mystery", 10749: "romance", 878: "scifi", 10770: "tv_movie",
    53: "thriller", 10752: "war", 37: "western"
}


def init_db(conn):
    cursor = conn.cursor()
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS movies
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY,
                       title
                       TEXT,
                       imdb_score
                       REAL,
                       release_date
                       TEXT,
                       genres
                       TEXT,
                       updated_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   """)
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS movie_providers
                   (
                       movie_id
                       INTEGER,
                       platform
                       TEXT,
                       region
                       TEXT,
                       PRIMARY
                       KEY
                   (
                       movie_id,
                       platform,
                       region
                   ),
                       FOREIGN KEY
                   (
                       movie_id
                   ) REFERENCES movies
                   (
                       id
                   )
                       )
                   """)
    conn.commit()


def sync_movies():
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY environment variable is missing.")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cursor = conn.cursor()

    # Clear previous snapshot completely
    cursor.execute("DELETE FROM movie_providers")
    cursor.execute("DELETE FROM movies")

    # Fetch 500 trending movies (25 pages * 20 movies/page)
    raw_movies = []
    seen_ids = set()
    target_count = 500

    print(f"Fetching top {target_count} trending movies from TMDB...")

    for page in range(1, 26):  # 25 pages = 500 movies
        url = "https://api.themoviedb.org/3/trending/movie/week"
        params = {"api_key": TMDB_API_KEY, "page": page}
        res = requests.get(url, params=params)

        if res.status_code == 200:
            results = res.json().get("results", [])
            for item in results:
                m_id = item.get("id")
                if m_id and m_id not in seen_ids:
                    seen_ids.add(m_id)
                    raw_movies.append(item)
                    if len(raw_movies) >= target_count:
                        break
        else:
            print(f"[WARN] Failed to fetch page {page}: {res.status_code}")

        if len(raw_movies) >= target_count:
            break

    print(f"Total unique movies retrieved: {len(raw_movies)}")

    # Insert movies & fetch Watch Providers dynamically for ALL flatrate services
    for index, movie in enumerate(raw_movies, 1):
        m_id = movie.get("id")
        title = movie.get("title")
        score = movie.get("vote_average", 0.0)
        rel_date = movie.get("release_date", "")
        genre_ids = movie.get("genre_ids", [])
        genres = ",".join([GENRE_MAP[g] for g in genre_ids if g in GENRE_MAP])

        # Store movie details
        cursor.execute("""
        INSERT OR REPLACE INTO movies (id, title, imdb_score, release_date, genres)
        VALUES (?, ?, ?, ?, ?)
        """, (m_id, title, score, rel_date, genres))

        # Fetch provider info from TMDB Watch Providers API
        prov_url = f"https://api.themoviedb.org/3/movie/{m_id}/watch/providers"
        prov_res = requests.get(prov_url, params={"api_key": TMDB_API_KEY})

        if prov_res.status_code == 200:
            reg_data = prov_res.json().get("results", {}).get(REGION, {})
            flatrate = reg_data.get("flatrate", [])

            for provider in flatrate:
                provider_name = provider.get("provider_name", "").strip()
                if provider_name:
                    cursor.execute("""
                                   INSERT
                                   OR IGNORE INTO movie_providers (movie_id, platform, region)
                    VALUES (?, ?, ?)
                                   """, (m_id, provider_name, REGION))

        if index % 50 == 0 or index == len(raw_movies):
            print(f"Processed {index}/{len(raw_movies)} movies...")

    conn.commit()
    conn.close()
    print(f"Successfully synced {len(raw_movies)} trending movies and all available streaming providers to {DB_PATH}.")


if __name__ == "__main__":
    sync_movies()