import logging

from src.clients.steamspy_client import SteamSpyClient
from src.config import Settings
from src.storage.state_manager import StateManager

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Odpowiada za pobieranie całego katalogu gier ze SteamSpy oraz ich wstępne filtrowanie."""

    def __init__(
        self,
        state_manager: StateManager,
        steamspy_client: SteamSpyClient,
        settings: Settings,
    ) -> None:
        """Inicjalizuje serwis pobierania katalogu, przypisując menedżer stanu, klienta API i konfigurację."""
        self.state_manager = state_manager
        self.steamspy_client = steamspy_client
        self.settings = settings

    def fetch_catalog(self, max_pages: int = 100) -> int:
        """Pobiera kolejne strony katalogu ze SteamSpy, zaczynając od miejsca, w którym ostatnio skończyliśmy."""
        last_page = self.state_manager.get_last_fetched_steamspy_page()
        start_page = 0 if last_page is None else last_page + 1
        total_saved = 0

        if start_page >= max_pages:
            logger.info(
                "Katalog SteamSpy jest już pobranym do strony %d (limit: %d).",
                last_page,
                max_pages,
            )
            return 0

        for page in range(start_page, max_pages):
            logger.info("Pobieranie strony %d/%d z API SteamSpy...", page, max_pages - 1)
            payload = self.steamspy_client.fetch_games_page(page)

            # Pusta odpowiedź oznacza, że dotarliśmy do końca katalogu wcześniej niż wynosi max_pages.
            if not payload:
                logger.info("Otrzymano pustą stronę %d. Kończymy pobieranie katalogu.", page)
                break

            saved_count = self.state_manager.save_steamspy_page(page, payload)
            total_saved += saved_count
            logger.info("Zapisano %d gier ze strony %d.", saved_count, page)

        return total_saved

    def filter_by_review_volume(self) -> dict[str, int]:
        """Odrzuca gry, które mają zbyt mało recenzji, opierając się na progu z konfiguracji."""
        threshold = self.settings.min_reviews_threshold
        logger.info("Uruchamiamy filtrowanie gier (wymagane minimum: %d recenzji)...", threshold)
        result = self.state_manager.apply_review_threshold_filter(min_reviews=threshold)
        logger.info(
            "Wynik filtrowania: zakwalifikowano %d gier, odrzucono %d gier.",
            result["qualified"],
            result["skipped"],
        )
        return result
