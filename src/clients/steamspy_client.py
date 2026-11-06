from typing import Any

from src.clients.base_client import ApiClientError, BaseApiClient
from src.config import Settings


class SteamSpyClient(BaseApiClient):
    """Klient służący do pobierania katalogu gier z API SteamSpy."""

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta SteamSpy, biorąc ustawienia z głównej konfiguracji aplikacji."""
        super().__init__(
            base_url=settings.steamspy_base_url,
            rate_limit_seconds=settings.steamspy_rate_limit_seconds,
            timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.max_retries,
            cooldown_on_rate_limit=65.0,
        )

    def fetch_games_page(self, page: int) -> dict[str, dict[str, Any]]:
        """Pobiera jedną stronę listy gier ze SteamSpy dla wskazanego numeru strony."""
        if page < 0:
            raise ValueError("Numer strony (page) nie może być ujemny.")

        # Tutaj używamy słownika params, żeby dołączyć parametry do zapytania HTTP.
        # W tym przypadku przekazujemy żądanie pełnej listy ('request': 'all') oraz numer strony.
        payload = self._get_json(params={"request": "all", "page": page})

        if not isinstance(payload, dict):
            raise ApiClientError(
                f"Nieoczekiwany format odpowiedzi ze SteamSpy dla strony {page}: oczekiwano słownika."
            )
        return payload
