from typing import Any

import pytest

from src.storage.state_manager import IngestionStatus, StateManager


@pytest.fixture
def state_manager() -> StateManager:
    """Tworzy osobną bazę SQLite w pamięci RAM na potrzeby testów jednostkowych."""
    manager = StateManager(":memory:")
    yield manager
    manager.close()


@pytest.fixture
def sample_steamspy_payload() -> dict[str, dict[str, Any]]:
    """Zwraca przykładowe dane gier symulujące odpowiedź z API SteamSpy."""
    return {
        "730": {
            "appid": 730,
            "name": "Counter-Strike 2",
            "positive": 5000000,
            "negative": 700000,
        },
        "440": {
            "appid": 440,
            "name": "Team Fortress 2",
            "positive": 25,
            "negative": 10,
        },
        "999999": {
            "appid": 999999,
            "name": "Abandoned Indie Game",
            "positive": 5,
            "negative": 2,
        },
    }


def test_steamspy_page_tracking_and_initial_save(
    state_manager: StateManager,
    sample_steamspy_payload: dict[str, dict[str, Any]],
) -> None:
    """Sprawdza, czy zapis strony ze SteamSpy działa poprawnie i nadaje grom status DISCOVERED."""
    assert state_manager.get_last_fetched_steamspy_page() is None

    saved_count = state_manager.save_steamspy_page(page=0, games_payload=sample_steamspy_payload)

    assert saved_count == 3
    assert state_manager.get_last_fetched_steamspy_page() == 0

    summary = state_manager.get_status_summary()
    assert summary == {IngestionStatus.DISCOVERED.value: 3}


def test_review_threshold_filtering(
    state_manager: StateManager,
    sample_steamspy_payload: dict[str, dict[str, Any]],
) -> None:
    """Sprawdza, czy filtry poprawnie oddzielają gry z wystarczającą liczbą recenzji od odrzuconych."""
    state_manager.save_steamspy_page(page=0, games_payload=sample_steamspy_payload)

    result = state_manager.apply_review_threshold_filter(min_reviews=30)

    assert result["qualified"] == 2  # app_id 730 oraz 440 (łącznie >= 30 recenzji)
    assert result["skipped"] == 1  # app_id 999999 (tylko 7 recenzji, odrzucona)

    pending_ids = state_manager.get_pending_enrichment_ids()
    assert pending_ids == [440, 730]


def test_enrichment_lifecycle_and_retry_limits(
    state_manager: StateManager,
    sample_steamspy_payload: dict[str, dict[str, Any]],
) -> None:
    """Sprawdza cały cykl życia pobierania szczegółów: sukces, ponawianie po błędzie i blokadę limitu."""
    state_manager.save_steamspy_page(page=0, games_payload=sample_steamspy_payload)
    state_manager.apply_review_threshold_filter(min_reviews=30)

    # 1. Pomyślne pobranie danych dla app_id 730
    state_manager.mark_enrichment_completed(730, {"name": "CS2", "type": "game"})

    # 2. Błąd tymczasowy (np. timeout) dla app_id 440 – gra powinna wrócić do kolejki
    state_manager.mark_enrichment_failed(440, is_permanent=False)
    assert state_manager.get_pending_enrichment_ids(max_retries=2) == [440]

    # Po przekroczeniu limitu ponowień gra znika z kolejki do pobrania
    state_manager.mark_enrichment_failed(440, is_permanent=False)
    assert state_manager.get_pending_enrichment_ids(max_retries=2) == []

    summary = state_manager.get_status_summary()
    assert summary[IngestionStatus.COMPLETED.value] == 1
    assert summary[IngestionStatus.FAILED_ERROR.value] == 1
    assert summary[IngestionStatus.SKIPPED_LOW_VOLUME.value] == 1


def test_permanent_failure_excludes_from_queue(
    state_manager: StateManager,
    sample_steamspy_payload: dict[str, dict[str, Any]],
) -> None:
    """Sprawdza, czy trwały błąd (np. usunięta gra) od razu wyrzuca grę z kolejki."""
    state_manager.save_steamspy_page(page=0, games_payload=sample_steamspy_payload)
    state_manager.apply_review_threshold_filter(min_reviews=30)

    state_manager.mark_enrichment_failed(440, is_permanent=True)

    pending_ids = state_manager.get_pending_enrichment_ids()
    assert pending_ids == [730]
    assert state_manager.get_status_summary()[IngestionStatus.FAILED_NOT_FOUND.value] == 1


def test_idempotency_protects_completed_records(
    state_manager: StateManager,
    sample_steamspy_payload: dict[str, dict[str, Any]],
) -> None:
    """Sprawdza, czy ponowne pobranie strony ze SteamSpy nie nadpisuje gier, które mają już status COMPLETED."""
    state_manager.save_steamspy_page(page=0, games_payload=sample_steamspy_payload)
    state_manager.apply_review_threshold_filter(min_reviews=30)
    state_manager.mark_enrichment_completed(730, {"detailed": True})

    # Ponowne zapisanie tej samej strony ze SteamSpy
    state_manager.save_steamspy_page(page=0, games_payload=sample_steamspy_payload)

    summary = state_manager.get_status_summary()
    assert summary[IngestionStatus.COMPLETED.value] == 1
