from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_default_settings_initialization() -> None:
    """Weryfikuje poprawność domyślnych wartości konfiguracyjnych."""
    settings = Settings(_env_file=None)

    assert settings.sqlite_db_path == Path("data/raw/ingestion_state.db")
    assert settings.processed_data_dir == Path("data/processed")
    assert settings.steamspy_rate_limit_seconds == 61.0
    assert settings.steam_store_rate_limit_seconds == 1.6
    assert settings.min_reviews_threshold == 30
    assert settings.max_retries == 5


def test_environment_variables_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Weryfikuje nadpisywanie konfiguracji przez zmienne środowiskowe (np. z docker-compose)."""
    monkeypatch.setenv("MIN_REVIEWS_THRESHOLD", "50")
    monkeypatch.setenv("STEAMSPY_RATE_LIMIT_SECONDS", "65.5")
    monkeypatch.setenv("SQLITE_DB_PATH", "/tmp/custom_state.db")

    settings = Settings(_env_file=None)

    assert settings.min_reviews_threshold == 50
    assert settings.steamspy_rate_limit_seconds == 65.5
    assert settings.sqlite_db_path == Path("/tmp/custom_state.db")


def test_steamspy_rate_limit_validation_error() -> None:
    """Weryfikuje blokadę konfiguracji grożącej banem IP na SteamSpy (< 60s)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, steamspy_rate_limit_seconds=59.9)

    assert "nie może być mniejszy niż 60.0 sekund" in str(exc_info.value)


def test_steam_store_rate_limit_validation_error() -> None:
    """Weryfikuje blokadę konfiguracji przekraczającej limit 200 zapytań na 5 minut (< 1.5s)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, steam_store_rate_limit_seconds=1.2)

    assert "nie może być mniejszy niż 1.5 sekundy" in str(exc_info.value)


def test_ensure_directories_creates_paths(tmp_path: Path) -> None:
    """Weryfikuje automatyczne tworzenie katalogów dla warstw Bronze i Silver."""
    raw_db_path = tmp_path / "bronze" / "nested" / "state.db"
    silver_dir_path = tmp_path / "silver" / "parquet"

    settings = Settings(
        _env_file=None,
        sqlite_db_path=raw_db_path,
        processed_data_dir=silver_dir_path,
    )
    settings.ensure_directories()

    assert raw_db_path.parent.exists()
    assert raw_db_path.parent.is_dir()
    assert silver_dir_path.exists()
    assert silver_dir_path.is_dir()
