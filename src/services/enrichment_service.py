import logging

from src.clients.base_client import ApiClientError, RateLimitExceededError
from src.clients.steam_store_client import SteamStoreClient
from src.config import Settings
from src.storage.state_manager import StateManager

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Zarządza pobieraniem szczegółowych danych o grach z oficjalnego sklepu Steam."""

    def __init__(
        self,
        state_manager: StateManager,
        steam_store_client: SteamStoreClient,
        settings: Settings,
    ) -> None:
        """Inicjalizuje serwis pobierania szczegółów, przypisując menedżer stanu, klienta API i konfigurację."""
        self.state_manager = state_manager
        self.steam_store_client = steam_store_client
        self.settings = settings

    def process_enrichment_queue(
        self,
        batch_size: int = 100,
        max_total_games: int | None = None,
    ) -> dict[str, int]:
        """Przetwarza kolejkę gier, które czekają na pobranie szczegółowych danych ze sklepu Steam."""
        stats = {"completed": 0, "not_found": 0, "failed": 0}
        processed_count = 0

        while True:
            if max_total_games is not None and processed_count >= max_total_games:
                logger.info("Osiągnięto limit przetworzonych gier (%d).", max_total_games)
                break

            current_limit = batch_size
            if max_total_games is not None:
                current_limit = min(batch_size, max_total_games - processed_count)

            pending_ids = self.state_manager.get_pending_enrichment_ids(
                limit=current_limit,
                max_retries=self.settings.max_retries,
            )

            if not pending_ids:
                logger.info("Kolejka pobierania szczegółów jest pusta. Kończymy pracę.")
                break

            for app_id in pending_ids:
                try:
                    details = self.steam_store_client.fetch_app_details(app_id)
                    if details is not None:
                        self.state_manager.mark_enrichment_completed(app_id, details)
                        stats["completed"] += 1
                    else:
                        # Gra została usunięta ze sklepu lub jest niedostępna – oznaczamy jako trwale niedostępną.
                        self.state_manager.mark_enrichment_failed(app_id, is_permanent=True)
                        stats["not_found"] += 1

                except RateLimitExceededError:
                    # Twarda blokada IP – przerywamy działanie całego programu, żeby nie pogorszyć sprawy.
                    logger.error(
                        "Otrzymano twardą blokadę zapytaj dla app_id=%d. Bezpiecznie zatrzymujemy program.",
                        app_id,
                    )
                    raise

                except ApiClientError as exc:
                    # Chwilowy błąd (np. problem z siecią dla konkretnej gry) – zapisujemy błąd i lecimy dalej.
                    logger.warning("Błąd pobierania danych dla app_id=%d: %s", app_id, str(exc))
                    self.state_manager.mark_enrichment_failed(app_id, is_permanent=False)
                    stats["failed"] += 1

                processed_count += 1

        return stats
