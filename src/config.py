from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Przechowuje i waliduje konfigurację aplikacji ładowaną ze zmiennych środowiskowych."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sqlite_db_path: Path = Field(
        default=Path("data/raw/ingestion_state.db"),
        description="Ścieżka do pliku bazy SQLite przechowującej stan pobierania (Warstwa Bronze).",
    )
    processed_data_dir: Path = Field(
        default=Path("data/processed"),
        description="Katalog docelowy dla wyczyszczonego pliku Parquet (Warstwa Silver).",
    )

    steamspy_base_url: str = Field(
        default="https://steamspy.com/api.php",
        description="Bazowy adres URL dla API SteamSpy.",
    )
    steam_store_base_url: str = Field(
        default="https://store.steampowered.com/api/appdetails",
        description="Bazowy adres URL dla oficjalnego API sklepu Steam.",
    )

    steamspy_rate_limit_seconds: float = Field(
        default=61.0,
        description="Odstęp czasowy między zapytaniami do SteamSpy (w sekundach).",
    )
    steam_store_rate_limit_seconds: float = Field(
        default=1.6,
        description="Odstęp czasowy między zapytaniami do Steam Store API (w sekundach).",
    )

    min_reviews_threshold: int = Field(
        default=100,
        ge=0,
        description="Minimalna łączna liczba recenzji (pozytywne + negatywne) kwalifikująca grę do analizy.",
    )
    max_retries: int = Field(
        default=5,
        ge=1,
        description="Maksymalna liczba ponowień zapytania HTTP w przypadku błędów przejściowych.",
    )
    http_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="Maksymalny czas oczekiwania na odpowiedź serwera HTTP (w sekundach).",
    )

    @field_validator("steamspy_rate_limit_seconds")
    @classmethod
    def validate_steamspy_rate_limit(cls, value: float) -> float:
        """Waliduje limit zapytań dla SteamSpy pod kątem rygorystycznych restrykcji IP."""
        if value < 60.0:
            raise ValueError(
                "Limit dla SteamSpy (steamspy_rate_limit_seconds) nie może być mniejszy niż 60.0 sekund."
            )
        return value

    @field_validator("steam_store_rate_limit_seconds")
    @classmethod
    def validate_steam_store_rate_limit(cls, value: float) -> float:
        """Waliduje limit zapytań dla Steam Store API (limit: 200 req / 5 min)."""
        if value < 1.5:
            raise ValueError(
                "Limit dla Steam Store (steam_store_rate_limit_seconds) nie może być mniejszy niż 1.5 sekundy."
            )
        return value

    def ensure_directories(self) -> None:
        """Tworzy strukturę katalogów dla warstw danych, jeśli jeszcze nie istnieją."""
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Tworzy i zwraca instancję konfiguracji aplikacji."""
    settings = Settings()
    settings.ensure_directories()
    return settings
