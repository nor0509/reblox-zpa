import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ApiClientError(Exception):
    """Ogólny błąd związany z komunikacją z zewnętrznym API."""


class RateLimitExceededError(ApiClientError):
    """Błąd zgłaszany wtedy, gdy wyczerpaliśmy limit prób po zablokowaniu zapytania przez serwer (HTTP 429/403)."""


class BaseApiClient:
    """Podstawowy klient HTTP, który dba o odpowiednie przerwy między zapytaniami i automatycznie ponawia próby w razie błędów.

    Pilnuje odstępów czasowych, żeby nie dostać bana na IP, oraz wstrzymuje ruch w przypadku blokady przez serwer.
    """

    def __init__(
        self,
        base_url: str,
        rate_limit_seconds: float,
        timeout_seconds: float = 30.0,
        max_retries: int = 5,
        cooldown_on_rate_limit: float = 300.0,
    ) -> None:
        """Inicjalizuje klienta HTTP ustawiając adres, limity czasu i czasy oczekiwania."""
        self.base_url = base_url
        self.rate_limit_seconds = rate_limit_seconds
        self.max_retries = max_retries
        self.cooldown_on_rate_limit = cooldown_on_rate_limit
        self._last_request_timestamp: float | None = None

        # Ustawiamy nagłówek User-Agent, żeby Steam nie odrzucał naszych zapytań jako podejrzanego ruchu.
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "SteamNicheFinder/0.1.0 (Data Engineering Pipeline)"},
            follow_redirects=True,
        )

    def _enforce_rate_limit(self) -> None:
        """Wstrzymuje działanie programu, aby zachować wymaganą przerwę czasową między zapytaniami."""
        if self._last_request_timestamp is not None:
            elapsed = time.monotonic() - self._last_request_timestamp
            remaining_wait = self.rate_limit_seconds - elapsed
            if remaining_wait > 0:
                time.sleep(remaining_wait)

    def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Wykonuje zapytanie GET, obsługując limity zapytań oraz ponowne próby w przypadku błędów."""
        for attempt in range(1, self.max_retries + 1):
            self._enforce_rate_limit()
            self._last_request_timestamp = time.monotonic()

            try:
                response = self._client.get(self.base_url, params=params)

                # Steam Store API potrafi zwrócić HTTP 403 zamiast 429 przy zbyt dużej liczbie zapytań.
                if response.status_code in (429, 403):
                    logger.warning(
                        "Otrzymano blokadę Rate Limit (HTTP %d). Próba %d/%d. Czekamy %.1f s.",
                        response.status_code,
                        attempt,
                        self.max_retries,
                        self.cooldown_on_rate_limit,
                    )
                    if attempt == self.max_retries:
                        raise RateLimitExceededError(
                            f"Przekroczono limit prób po blokadzie HTTP {response.status_code} dla parametrów {params}."
                        )
                    time.sleep(self.cooldown_on_rate_limit)
                    continue

                if response.status_code >= 500:
                    backoff = float(2**attempt)
                    logger.warning(
                        "Błąd po stronie serwera (HTTP %d). Próba %d/%d. Ponawiamy za %.1f s.",
                        response.status_code,
                        attempt,
                        self.max_retries,
                        backoff,
                    )
                    if attempt == self.max_retries:
                        raise ApiClientError(
                            f"Trwały błąd serwera HTTP {response.status_code} dla parametrów {params}."
                        )
                    time.sleep(backoff)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPError as exc:
                backoff = float(2**attempt)
                logger.warning(
                    "Problem z połączeniem sieciowym (%s). Próba %d/%d. Ponawiamy za %.1f s.",
                    str(exc),
                    attempt,
                    self.max_retries,
                    backoff,
                )
                if attempt == self.max_retries:
                    raise ApiClientError(f"Błąd komunikacji sieciowej: {exc}") from exc
                time.sleep(backoff)

            except ValueError as exc:
                # Steam czasami zwraca stronę HTML zamiast JSON podczas awarii lub prac serwisowych.
                backoff = float(2**attempt)
                logger.warning(
                    "Serwer nie zwrócił poprawnego formatu JSON. Próba %d/%d.",
                    attempt,
                    self.max_retries,
                )
                if attempt == self.max_retries:
                    raise ApiClientError("Serwer zwrócił niepoprawny format JSON.") from exc
                time.sleep(backoff)

        raise ApiClientError("Przekroczono maksymalną liczbę prób wykonania zapytania.")

    def close(self) -> None:
        """Zamyka połączenia klienta HTTP."""
        self._client.close()

    def __enter__(self) -> "BaseApiClient":
        """Pozwala używać klienta w bloku 'with'."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Automatycznie zamyka połączenie przy wychodzeniu z bloku 'with'."""
        self.close()
