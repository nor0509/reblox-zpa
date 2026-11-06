import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import duckdb

from src.storage.state_manager import IngestionStatus

logger = logging.getLogger(__name__)


class ParquetExporter:
    """Konwertuje pobrane dane z bazy SQLite do plików w formacie Apache Parquet."""

    def __init__(self, sqlite_db_path: Path | str, processed_dir: Path | str) -> None:
        """Inicjalizuje eksporter, ustawiając ścieżkę do bazy SQLite oraz folder docelowy dla plików Parquet."""
        self.sqlite_db_path = Path(sqlite_db_path)
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _extract_raw_rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Odczytuje dane z bazy SQLite i przekształca je do płaskich słowników gotowych do zapisania w plikach."""
        games_rows: list[dict[str, Any]] = []
        tags_rows: list[dict[str, Any]] = []

        conn = sqlite3.connect(str(self.sqlite_db_path))
        try:
            cursor = conn.execute(
                """
                SELECT app_id, raw_steamspy_json, raw_steam_json
                FROM games_ingestion_state
                WHERE status = ? AND raw_steam_json IS NOT NULL;
                """,
                (IngestionStatus.COMPLETED.value,),
            )

            for app_id, spy_json_str, steam_json_str in cursor:
                spy_data: dict[str, Any] = json.loads(spy_json_str)
                steam_data: dict[str, Any] = json.loads(steam_json_str)

                price_overview = steam_data.get("price_overview") or {}
                release_date = steam_data.get("release_date") or {}
                platforms = steam_data.get("platforms") or {}
                metacritic = steam_data.get("metacritic") or {}
                recommendations = steam_data.get("recommendations") or {}

                # Ceny w API Steama są podawane w centach – przeliczamy je na dolary.
                initial_cents = price_overview.get("initial")
                final_cents = price_overview.get("final")

                games_rows.append(
                    {
                        "app_id": int(app_id),
                        "name": steam_data.get("name") or spy_data.get("name"),
                        "type": steam_data.get("type"),
                        "is_free": bool(steam_data.get("is_free", False)),
                        "release_date": release_date.get("date"),
                        "coming_soon": bool(release_date.get("coming_soon", False)),
                        "price_initial_usd": (
                            round(initial_cents / 100.0, 2) if initial_cents is not None else 0.0
                        ),
                        "price_final_usd": (
                            round(final_cents / 100.0, 2) if final_cents is not None else 0.0
                        ),
                        "discount_percent": int(price_overview.get("discount_percent", 0)),
                        "positive_reviews": int(spy_data.get("positive", 0) or 0),
                        "negative_reviews": int(spy_data.get("negative", 0) or 0),
                        "total_recommendations": int(recommendations.get("total", 0) or 0),
                        "owners_range": str(spy_data.get("owners", "")),
                        "average_playtime_forever_min": int(
                            spy_data.get("average_forever", 0) or 0
                        ),
                        "median_playtime_forever_min": int(spy_data.get("median_forever", 0) or 0),
                        "ccu": int(spy_data.get("ccu", 0) or 0),
                        "metacritic_score": (
                            int(metacritic["score"]) if "score" in metacritic else None
                        ),
                        "required_age": int(
                            str(steam_data.get("required_age", 0)).replace("+", "") or 0
                        ),
                        "windows": bool(platforms.get("windows", False)),
                        "mac": bool(platforms.get("mac", False)),
                        "linux": bool(platforms.get("linux", False)),
                        "developers": ", ".join(steam_data.get("developers") or []),
                        "publishers": ", ".join(steam_data.get("publishers") or []),
                        "genres": ", ".join(
                            g["description"]
                            for g in (steam_data.get("genres") or [])
                            if isinstance(g, dict) and "description" in g
                        ),
                        "categories": ", ".join(
                            c["description"]
                            for c in (steam_data.get("categories") or [])
                            if isinstance(c, dict) and "description" in c
                        ),
                        "short_description": steam_data.get("short_description"),
                    }
                )

                # Tagi zapisujemy osobno, bo każda gra ma ich całą listę.
                raw_tags = spy_data.get("tags")
                if isinstance(raw_tags, dict):
                    for tag_name, vote_count in raw_tags.items():
                        tags_rows.append(
                            {
                                "app_id": int(app_id),
                                "tag_name": str(tag_name),
                                "votes": int(vote_count),
                            }
                        )
        finally:
            conn.close()

        return games_rows, tags_rows

    def export_to_parquet(self) -> dict[str, int]:
        """Zapisuje przygotowane dane do plików games.parquet oraz tags.parquet."""
        games_rows, tags_rows = self._extract_raw_rows()

        games_parquet_path = self.processed_dir / "games.parquet"
        tags_parquet_path = self.processed_dir / "tags.parquet"

        # Używamy DuckDB w pamięci RAM, żeby szybko przekonwertować dane na skompresowany format Parquet.
        duck_conn = duckdb.connect(":memory:")
        try:
            duck_conn.execute(
                """
                CREATE TABLE games (
                    app_id INTEGER,
                    name VARCHAR,
                    type VARCHAR,
                    is_free BOOLEAN,
                    release_date VARCHAR,
                    coming_soon BOOLEAN,
                    price_initial_usd DOUBLE,
                    price_final_usd DOUBLE,
                    discount_percent INTEGER,
                    positive_reviews INTEGER,
                    negative_reviews INTEGER,
                    total_recommendations INTEGER,
                    owners_range VARCHAR,
                    average_playtime_forever_min INTEGER,
                    median_playtime_forever_min INTEGER,
                    ccu INTEGER,
                    metacritic_score INTEGER,
                    required_age INTEGER,
                    windows BOOLEAN,
                    mac BOOLEAN,
                    linux BOOLEAN,
                    developers VARCHAR,
                    publishers VARCHAR,
                    genres VARCHAR,
                    categories VARCHAR,
                    short_description VARCHAR
                );
                """
            )
            duck_conn.execute(
                """
                CREATE TABLE tags (
                    app_id INTEGER,
                    tag_name VARCHAR,
                    votes INTEGER
                );
                """
            )

            if games_rows:
                duck_conn.executemany(
                    """
                    INSERT INTO games VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    );
                    """,
                    [list(row.values()) for row in games_rows],
                )

            if tags_rows:
                duck_conn.executemany(
                    "INSERT INTO tags VALUES (?, ?, ?);",
                    [list(row.values()) for row in tags_rows],
                )

            duck_conn.execute(
                f"COPY games TO '{games_parquet_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);"
            )
            duck_conn.execute(
                f"COPY tags TO '{tags_parquet_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);"
            )
        finally:
            duck_conn.close()

        stats = {"games": len(games_rows), "tags": len(tags_rows)}
        logger.info(
            "Eksport do Parquet zakończony: zapisano %d gier i %d tagów.",
            stats["games"],
            stats["tags"],
        )
        return stats
