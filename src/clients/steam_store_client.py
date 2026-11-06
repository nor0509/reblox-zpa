from typing import Any

from src.clients.base_client import ApiClientError, BaseApiClient
from src.config import Settings


class SteamStoreClient(BaseApiClient):
    """Klient służący do pobierania szczegółowych danych o grach z oficjalnego sklepu Steam."""

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta sklepu Steam na podstawie głównej konfiguracji aplikacji."""
        super().__init__(
            base_url=settings.steam_store_base_url,
            rate_limit_seconds=settings.steam_store_rate_limit_seconds,
            timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.max_retries,
            cooldown_on_rate_limit=300.0,
        )

    def fetch_app_details(self, app_id: int) -> dict[str, Any] | None:
        """Pobiera szczegółowe informacje o konkretnej grze z oficjalnego sklepu Steam."""
        app_id_str = str(app_id)

        # Wymuszamy region USA (cc=us) i język angielski (l=english),
        # żeby ceny były w dolarach, a nazwy tagów i gatunków były jednolite dla całej bazy.
        payload = self._get_json(params={"appids": app_id_str, "cc": "us", "l": "english"})

        if not isinstance(payload, dict) or app_id_str not in payload:
            raise ApiClientError(
                f"Brak danych dla gry o ID {app_id_str} w odpowiedzi ze Steam Store API."
            )

        app_entry = payload[app_id_str]
        if not isinstance(app_entry, dict):
            raise ApiClientError(f"Niepoprawny format danych dla gry o ID {app_id_str}.")

        # Jeśli gra została wycofana ze sklepu, Steam potrafi zwrócić HTTP 200,
        # ale z flagą success=false. Zwracamy wtedy None, żeby oznaczyć grę jako niedostępną.
        if not app_entry.get("success", False):
            return None

        data = app_entry.get("data")
        return data if isinstance(data, dict) else None
