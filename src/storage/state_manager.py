import json
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class IngestionStatus(StrEnum):
    """Reprezentuje stany cyklu życia gry w procesie pobierania danych."""

    DISCOVERED = "DISCOVERED"
    PENDING_ENRICHMENT = "PENDING_ENRICHMENT"
    SKIPPED_LOW_VOLUME = "SKIPPED_LOW_VOLUME"
    COMPLETED = "COMPLETED"
    FAILED_NOT_FOUND = "FAILED_NOT_FOUND"
    FAILED_ERROR = "FAILED_ERROR"


class StateManager:
    """Klasa StateManager zarządza zapisywaniem i kontrolowaniem postępu pobierania danych w pliku bazy SQLite.

    Odpowiada za:
    - Śledzenie postępu: Pamięta, które strony ze SteamSpy zostały już ściągnięte, dzięki czemu w przypadku awarii program nie zaczyna pracy od zera.
    - Pilnowanie etapu dla każdej gry: Śledzi status poszczególnych pozycji (np. czy gra została dopiero znaleziona, czy odrzucona przez zbyt małą liczbę recenzji, czy pobrano już o niej pełne informacje).
    - Zapisywanie surowych danych: Przechowuje oryginalne odpowiedzi z serwerów w bazie, co pozwala w każdej chwili wrócić do surowych informacji.
    """

    def __init__(self, db_path: Path | str) -> None:
        """Inicjalizuje menedżer stanu i tworzy tabele w bazie danych."""
        self.db_path = str(db_path)
        # Utrzymujemy jedno stałe połączenie dla baz w pamięci (in-memory),
        # żeby nie tracić tabel między wywołaniami w testach.
        self._persistent_conn: sqlite3.Connection | None = (
            sqlite3.connect(self.db_path) if self.db_path == ":memory:" else None
        )
        self._initialize_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Zwraca aktywne połączenie z bazą danych."""
        if self._persistent_conn is not None:
            return self._persistent_conn

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        # Włączamy tryb WAL, żeby baza pozwalała na jednoczesny odczyt i zapis
        # bez wyskakiwania błędu o zablokowaniu bazy.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _initialize_schema(self) -> None:
        """Tworzy niezbędne tabele w bazie danych, jeśli jeszcze nie istnieją."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS steamspy_pages (
                        page INTEGER PRIMARY KEY,
                        fetched_at TEXT NOT NULL,
                        games_count INTEGER NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS games_ingestion_state (
                        app_id INTEGER PRIMARY KEY,
                        status TEXT NOT NULL,
                        positive_reviews INTEGER NOT NULL DEFAULT 0,
                        negative_reviews INTEGER NOT NULL DEFAULT 0,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        raw_steamspy_json TEXT NOT NULL,
                        raw_steam_json TEXT,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                # Indeks przyspiesza wyszukiwanie gier po ich aktualnym statusie.
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_games_status
                    ON games_ingestion_state (status);
                    """
                )
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_last_fetched_steamspy_page(self) -> int | None:
        """Zwraca numer ostatniej pomyślnie pobranej strony ze SteamSpy."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT MAX(page) FROM steamspy_pages;")
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        finally:
            if self._persistent_conn is None:
                conn.close()

    def save_steamspy_page(self, page: int, games_payload: dict[str, dict[str, Any]]) -> int:
        """Zapisuje pobraną stronę ze SteamSpy wraz z podstawowymi informacjami o grach."""
        now_iso = datetime.now(UTC).isoformat()
        records_to_upsert: list[tuple[int, str, int, int, str, str]] = []

        for app_id_str, game_data in games_payload.items():
            # Pomijamy błędne klucze, które czasem trafiają się w odpowiedzi z API.
            if not str(app_id_str).isdigit():
                continue

            app_id = int(app_id_str)
            positive = int(game_data.get("positive", 0) or 0)
            negative = int(game_data.get("negative", 0) or 0)
            raw_json = json.dumps(game_data, ensure_ascii=False)

            records_to_upsert.append(
                (app_id, IngestionStatus.DISCOVERED.value, positive, negative, raw_json, now_iso)
            )

        conn = self._get_connection()
        try:
            with conn:
                # Jeśli gra już jest w bazie, aktualizujemy jej dane tylko wtedy,
                # gdy ma jeszcze status DISCOVERED (nie dotykamy ukończonych gier).
                conn.executemany(
                    """
                    INSERT INTO games_ingestion_state (
                        app_id, status, positive_reviews, negative_reviews,
                        raw_steamspy_json, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_id) DO UPDATE SET
                        positive_reviews = excluded.positive_reviews,
                        negative_reviews = excluded.negative_reviews,
                        raw_steamspy_json = excluded.raw_steamspy_json,
                        updated_at = excluded.updated_at
                    WHERE games_ingestion_state.status = 'DISCOVERED';
                    """,
                    records_to_upsert,
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO steamspy_pages (page, fetched_at, games_count)
                    VALUES (?, ?, ?);
                    """,
                    (page, now_iso, len(records_to_upsert)),
                )
            return len(records_to_upsert)
        finally:
            if self._persistent_conn is None:
                conn.close()

    def apply_review_threshold_filter(self, min_reviews: int) -> dict[str, int]:
        """Dzieli gry na te, które spełniają wymagany próg recenzji, i te, które odrzucamy."""
        now_iso = datetime.now(UTC).isoformat()
        conn = self._get_connection()
        try:
            with conn:
                qualified_cursor = conn.execute(
                    """
                    UPDATE games_ingestion_state
                    SET status = ?, updated_at = ?
                    WHERE status = ? AND (positive_reviews + negative_reviews) >= ?;
                    """,
                    (
                        IngestionStatus.PENDING_ENRICHMENT.value,
                        now_iso,
                        IngestionStatus.DISCOVERED.value,
                        min_reviews,
                    ),
                )
                skipped_cursor = conn.execute(
                    """
                    UPDATE games_ingestion_state
                    SET status = ?, updated_at = ?
                    WHERE status = ? AND (positive_reviews + negative_reviews) < ?;
                    """,
                    (
                        IngestionStatus.SKIPPED_LOW_VOLUME.value,
                        now_iso,
                        IngestionStatus.DISCOVERED.value,
                        min_reviews,
                    ),
                )
                return {
                    "qualified": qualified_cursor.rowcount,
                    "skipped": skipped_cursor.rowcount,
                }
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_pending_enrichment_ids(self, limit: int = 100, max_retries: int = 5) -> list[int]:
        """Pobiera listę ID gier, które czekają na szczegółowe pobranie danych ze sklepu Steam."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT app_id
                FROM games_ingestion_state
                WHERE status = ?
                   OR (status = ? AND retry_count < ?)
                ORDER BY app_id ASC
                LIMIT ?;
                """,
                (
                    IngestionStatus.PENDING_ENRICHMENT.value,
                    IngestionStatus.FAILED_ERROR.value,
                    max_retries,
                    limit,
                ),
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            if self._persistent_conn is None:
                conn.close()

    def mark_enrichment_completed(self, app_id: int, steam_store_data: dict[str, Any]) -> None:
        """Zapisuje pobrane dane ze sklepu Steam i oznacza grę jako w pełni przetworzoną."""
        now_iso = datetime.now(UTC).isoformat()
        raw_json = json.dumps(steam_store_data, ensure_ascii=False)
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE games_ingestion_state
                    SET status = ?, raw_steam_json = ?, updated_at = ?
                    WHERE app_id = ?;
                    """,
                    (IngestionStatus.COMPLETED.value, raw_json, now_iso, app_id),
                )
        finally:
            if self._persistent_conn is None:
                conn.close()

    def mark_enrichment_failed(self, app_id: int, is_permanent: bool = False) -> None:
        """Zapisuje informację o błędzie podczas pobierania danych gry ze sklepu."""
        now_iso = datetime.now(UTC).isoformat()
        target_status = (
            IngestionStatus.FAILED_NOT_FOUND.value
            if is_permanent
            else IngestionStatus.FAILED_ERROR.value
        )
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE games_ingestion_state
                    SET status = ?, retry_count = retry_count + 1, updated_at = ?
                    WHERE app_id = ?;
                    """,
                    (target_status, now_iso, app_id),
                )
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_status_summary(self) -> dict[str, int]:
        """Zwraca podsumowanie liczby gier w poszczególnych statusach."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM games_ingestion_state
                GROUP BY status;
                """
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
        finally:
            if self._persistent_conn is None:
                conn.close()

    def close(self) -> None:
        """Zamyka stałe połączenie z bazą danych (używane w testach)."""
        if self._persistent_conn is not None:
            self._persistent_conn.close()
            self._persistent_conn = None
