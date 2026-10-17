import json
import os
import time

import requests


def fetch_parsed_steam_data(app_id: str) -> dict | None:
    """
    Pobiera i parsuje kluczowe zmienne celu oraz cechy wejściowe dla modelu ze Steam API.

    Args:
        app_id (str): ID gry w ekosystemie Steam (np. "105600").

    Returns:
        dict: Słownik zawierający wyczyszczone metryki gotowe do analizy nisz rynkowych.
        None: W przypadku błędu HTTP lub odrzucenia połączenia.
    """
    url_spy = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
    url_store = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp_spy = requests.get(url_spy, headers=headers, timeout=10)
        resp_store = requests.get(url_store, headers=headers, timeout=10)

        if resp_spy.status_code == 200 and resp_store.status_code == 200:
            data_spy = resp_spy.json()
            store_json = resp_store.json()

            # Ekstrakcja danych ze Steam Store API
            data_store = (
                store_json.get(app_id, {}).get("data", {})
                if store_json.get(app_id, {}).get("success")
                else {}
            )

            # Bezpieczne rzutowanie ceny na typ zmiennoprzecinkowy
            raw_price = data_spy.get("initialprice") or "0"
            base_price = float(raw_price) / 100.0

            return {
                "app_id": app_id,
                "name": data_spy.get("name", "Nieznana gra"),
                "type": data_store.get("type", "Brak typu"),
                "release_date": data_store.get("release_date", {}).get(
                    "date", "Brak daty"
                ),
                "owners": data_spy.get("owners", "Brak"),
                "positive": int(data_spy.get("positive") or 0),
                "negative": int(data_spy.get("negative") or 0),
                "average_forever": data_spy.get("average_forever", 0),
                "ccu": data_spy.get("ccu", 0),
                "metacritic": data_store.get("metacritic", {}).get(
                    "score", "Brak oceny"
                ),
                "base_price": base_price,
                "is_free": data_store.get("is_free", False),
                "tags": data_spy.get("tags", {}),
                "categories": [
                    cat.get("description") for cat in data_store.get("categories", [])
                ],
                "supported_languages": data_store.get(
                    "supported_languages", "Brak danych"
                )
                .replace("<br><strong>*</strong>", "")
                .split(", "),
            }

        print(
            f"[ERROR] Błąd HTTP dla {app_id}: Spy: {resp_spy.status_code}, Store: {resp_store.status_code}"
        )
        return None

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Wyjątek podczas łączenia dla {app_id}: {e}")
        return None


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # Lista testowa (Terraria oraz przykładowe ID)
    app_ids_to_scrape = ["105600", "292030"]
    scraped_data = []

    for app_id in app_ids_to_scrape:
        print(f"Pobieranie danych dla AppID: {app_id}...")
        parsed_data = fetch_parsed_steam_data(app_id)

        if parsed_data:
            scraped_data.append(parsed_data)

        # Wymuszone opóźnienie w celu ominięcia blokad Rate Limiting API
        time.sleep(1.5)

    # Zapis zagregowanych wyników do jednego pliku w docelowym katalogu
    file_path = "data/test/steam_dataset_test.json"

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(scraped_data, f, indent=4, ensure_ascii=False)

    print(f"Pobieranie zakończone. Dane zapisano w: {file_path}")
