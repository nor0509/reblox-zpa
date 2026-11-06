import logging
import sys

import typer
from rich.console import Console
from rich.table import Table

from src.clients.steam_store_client import SteamStoreClient
from src.clients.steamspy_client import SteamSpyClient
from src.config import get_settings
from src.services.discovery_service import DiscoveryService
from src.services.enrichment_service import EnrichmentService
from src.storage.exporter import ParquetExporter
from src.storage.state_manager import StateManager

# Konfiguracja logowania do strumienia wyjściowego (stdout) dla kontenerów i terminala.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

app = typer.Typer(
    name="steam-pipeline",
    help="Narzędzie do pobierania danych o grach ze Steam i eksportu do plików Parquet.",
    add_completion=False,
)
console = Console()


@app.command()
def discover(
    max_pages: int = typer.Option(
        100, "--max-pages", "-p", help="Maksymalna liczba stron do pobrania ze SteamSpy."
    ),
) -> None:
    """Krok 1: Pobiera listę gier ze SteamSpy i zapisuje postęp w bazie SQLite."""
    settings = get_settings()
    state_manager = StateManager(settings.sqlite_db_path)
    with SteamSpyClient(settings) as client:
        service = DiscoveryService(state_manager, client, settings)
        saved = service.fetch_catalog(max_pages=max_pages)
        console.print(
            f"[bold green]Zakończono pobieranie katalogu. Zapisano gier: {saved}[/bold green]"
        )


@app.command(name="filter")
def filter_games() -> None:
    """Krok 2: Odrzuca gry, które mają zbyt mało recenzji."""
    settings = get_settings()
    state_manager = StateManager(settings.sqlite_db_path)
    with SteamSpyClient(settings) as client:
        service = DiscoveryService(state_manager, client, settings)
        result = service.filter_by_review_volume()
        console.print(
            f"[bold cyan]Wynik filtrowania:[/bold cyan] Zakwalifikowano: {result['qualified']} | Odrzucono: {result['skipped']}"
        )


@app.command()
def enrich(
    batch_size: int = typer.Option(
        100, "--batch-size", "-b", help="Liczba gier pobieranych naraz w jednej paczce."
    ),
    max_games: int | None = typer.Option(
        None, "--max-games", "-m", help="Limit gier do przetworzenia w tym uruchomieniu."
    ),
) -> None:
    """Krok 3: Pobiera szczegółowe informacje o grach z oficjalnego sklepu Steam."""
    settings = get_settings()
    state_manager = StateManager(settings.sqlite_db_path)
    with SteamStoreClient(settings) as client:
        service = EnrichmentService(state_manager, client, settings)
        stats = service.process_enrichment_queue(batch_size=batch_size, max_total_games=max_games)
        console.print(
            f"[bold green]Zakończono pobieranie szczegółów:[/bold green] Sukces: {stats['completed']} | "
            f"Brak w sklepie: {stats['not_found']} | Błędy: {stats['failed']}"
        )


@app.command()
def export() -> None:
    """Krok 4: Eksportuje dane z bazy SQLite do gotowych plików Parquet."""
    settings = get_settings()
    exporter = ParquetExporter(
        sqlite_db_path=settings.sqlite_db_path,
        processed_dir=settings.processed_data_dir,
    )
    stats = exporter.export_to_parquet()
    console.print(
        f"[bold green]Wygenerowano pliki w {settings.processed_data_dir}:[/bold green] "
        f"games.parquet ({stats['games']} wierszy)"
    )


@app.command()
def status() -> None:
    """Pokazuje aktualny stan przetwarzania gier zapisany w bazie SQLite."""
    settings = get_settings()
    state_manager = StateManager(settings.sqlite_db_path)
    summary = state_manager.get_status_summary()
    last_page = state_manager.get_last_fetched_steamspy_page()

    table = Table(title=f"Stan bazy (Ostatnia pobrana strona SteamSpy: {last_page})")
    table.add_column("Status", style="cyan", no_wrap=True)
    table.add_column("Liczba Gier", justify="right", style="magenta")

    for state_name, count in sorted(summary.items()):
        table.add_row(state_name, str(count))

    console.print(table)


@app.command(name="run-all")
def run_all(
    max_pages: int = typer.Option(
        100, "--max-pages", "-p", help="Maksymalna liczba stron do pobrania ze SteamSpy."
    ),
    max_games: int | None = typer.Option(
        None, "--max-games", "-m", help="Limit gier do przetworzenia w sklepie Steam."
    ),
) -> None:
    """Uruchamia pełny proces po kolei: Pobieranie -> Filtrowanie -> Szczegóły -> Eksport."""
    discover(max_pages=max_pages)
    filter_games()
    enrich(batch_size=100, max_games=max_games)
    export()


if __name__ == "__main__":
    app()
