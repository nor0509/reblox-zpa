import httpx
import pytest
import respx

from src.clients.base_client import ApiClientError, RateLimitExceededError
from src.clients.steam_store_client import SteamStoreClient
from src.clients.steamspy_client import SteamSpyClient
from src.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Tworzy konfigurację testową z minimalnymi limitami czasowymi."""
    return Settings(
        _env_file=None,
        steamspy_rate_limit_seconds=60.0,
        steam_store_rate_limit_seconds=1.5,
        max_retries=3,
    )


@respx.mock
def test_steamspy_client_fetch_page_success(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sprawdza, czy klient SteamSpy poprawnie pobiera i zwraca stronę z listą gier."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    mock_payload = {"730": {"appid": 730, "name": "Counter-Strike 2"}}

    route = respx.get(test_settings.steamspy_base_url).mock(
        return_value=httpx.Response(200, json=mock_payload)
    )

    with SteamSpyClient(test_settings) as client:
        result = client.fetch_games_page(page=0)

    assert route.called
    assert result == mock_payload


@respx.mock
def test_steam_store_client_fetch_details_success_and_not_found(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sprawdza, czy klient sklepu Steam poprawnie wyciąga dane istniejącej gry i zwraca None dla usuniętej."""
    monkeypatch.setattr("time.sleep", lambda _: None)

    respx.get(
        test_settings.steam_store_base_url, params={"appids": "730", "cc": "us", "l": "english"}
    ).mock(
        return_value=httpx.Response(
            200,
            json={"730": {"success": True, "data": {"name": "CS2", "is_free": True}}},
        )
    )
    respx.get(
        test_settings.steam_store_base_url, params={"appids": "999", "cc": "us", "l": "english"}
    ).mock(
        return_value=httpx.Response(
            200,
            json={"999": {"success": False}},
        )
    )

    with SteamStoreClient(test_settings) as client:
        valid_game = client.fetch_app_details(730)
        removed_game = client.fetch_app_details(999)

    assert valid_game == {"name": "CS2", "is_free": True}
    assert removed_game is None


@respx.mock
def test_client_retries_on_429_and_eventually_succeeds(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sprawdza, czy po otrzymaniu błędu 429 program czeka i ponawia zapytanie, kończąc sukcesem."""
    sleep_calls: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    route = respx.get(test_settings.steam_store_base_url).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"730": {"success": True, "data": {"name": "CS2"}}}),
        ]
    )

    with SteamStoreClient(test_settings) as client:
        result = client.fetch_app_details(730)

    assert route.call_count == 2
    assert result == {"name": "CS2"}
    # Sprawdzamy, czy po błędzie 429 zastosowano 300-sekundową przerwę (cooldown).
    assert 300.0 in sleep_calls


@respx.mock
def test_client_raises_rate_limit_error_after_max_retries(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sprawdza, czy po wyczerpaniu wszystkich prób przy błędzie 429 wyrzucany jest wyjątek RateLimitExceededError."""
    monkeypatch.setattr("time.sleep", lambda _: None)

    respx.get(test_settings.steam_store_base_url).mock(return_value=httpx.Response(429))

    with SteamStoreClient(test_settings) as client, pytest.raises(RateLimitExceededError):
        client.fetch_app_details(730)


@respx.mock
def test_client_exponential_backoff_on_500_server_error(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sprawdza, czy przy błędach serwera (HTTP 500) czas oczekiwania rośnie wykładniczo (Exponential Backoff)."""
    sleep_calls: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    respx.get(test_settings.steamspy_base_url).mock(return_value=httpx.Response(500))

    with SteamSpyClient(test_settings) as client, pytest.raises(ApiClientError):
        client.fetch_games_page(0)

    # Przy 3 próbach przerwy wynoszą kolejno 2^1 = 2.0s oraz 2^2 = 4.0s.
    assert 2.0 in sleep_calls
    assert 4.0 in sleep_calls
