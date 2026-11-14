# SteamNicheFinder - Słownik Danych (Data Dictionary)

Niniejszy dokument określa specyfikację techniczną zmiennych w architekturze danych projektu **SteamNicheFinder**. Zbiór podzielono na warstwę **Bronze** (dane źródłowe) oraz **Silver** (dane oczyszczone i przetworzone).

## SPIS TREŚCI

1. [Warstwa Bronze (Raw / Staging)](#1-warstwa-bronze-raw--staging)
2. [Warstwa Silver (Cleaned & Feature Engineered)](#2-warstwa-silver-cleaned--feature-engineered)
   * [A. Cechy podstawowe i czyszczenie](#a-cechy-podstawowe-i-czyszczenie)
   * [B. Metryki jakości i ekonomiczne](#b-metryki-jakości-i-ekonomiczne)
   * [C. Transformacje pod modele ML](#c-transformacje-pod-modele-ml)
   * [D. Kontekst rynkowy](#d-kontekst-rynkowy)
   * [E. Zmienne celu](#e-zmienne-celu)
3. [Przypisy i Metodologia](#3-przypisy-i-metodologia)

---

## 1. Warstwa Bronze (Raw / Staging)

*Dane źródłowe pozyskane z API SteamSpy oraz Steam Store, zapisane w bazie SQLite i wyeksportowane do pliku `games.parquet`.*

1. **`app_id`** (`INTEGER`): Identyfikator numeryczny gry w systemie Steam. Klucz główny.
2. **`name`** (`VARCHAR`): Tytuł gry. Występują jednostkowe puste ciągi znaków.
3. **`type`** (`VARCHAR`): Kategoria obiektu w sklepie Steam (np. `game`).
4. **`is_free`** (`BOOLEAN`): Flaga statusu darmowego produktu (*Free-to-Play*).
5. **`release_date`** (`VARCHAR`): Surowy ciąg znaków określający datę premiery. Występują braki i niestandardowe formaty.
6. **`coming_soon`** (`BOOLEAN`): Flaga zapowiedzi produktu.
7. **`price_initial_usd` / `price_final_usd`** (`DOUBLE`): Cena katalogowa oraz końcowa w USD. Dla darmowych gier zwraca `0.0`.
8. **`discount_percent`** (`INTEGER`): Wielkość zniżki procentowej.
9. **`positive_reviews` / `negative_reviews`** (`INTEGER`): Liczba recenzji pozytywnych i negatywnych.
10. **`total_recommendations`** (`INTEGER`): Liczba rekomendacji w systemie Steam.
11. **`owners_range`** (`VARCHAR`): Tekstowy przedział liczby posiadaczy ze SteamSpy.
12. **`ccu`** (`INTEGER`): Szczytowa liczba jednocześnie grających użytkowników.
13. **`metacritic_score`** (`INTEGER`): Punktowa ocena krytyków (0–100). Występuje w ~17% rekordów; brakujące wartości przyjmują `NULL`.
14. **`required_age`** (`INTEGER`): Minimalny wiek gracza.
15. **`windows` / `mac` / `linux`** (`BOOLEAN`): Flagi kompatybilności systemowej.
16. **`developers` / `publishers`** (`VARCHAR`): Listy twórców i wydawców rozdzielone przecinkami. Występują puste stringi.
17. **`genres` / `categories`** (`VARCHAR`): Tekstowe listy gatunków i tagów funkcjonalnych. Występują puste stringi.
18. **`short_description`** (`VARCHAR`): Opis marketingowy gry. Występują jednostkowe braki.


| Kolumna | The Witcher 3 (292030) | Intruder (518150) | Lethal Company (1966720) |
| :--- | :--- | :--- | :--- |
| **app_id** | `292030` | `518150` | `1966720` |
| **name** | The Witcher 3: Wild Hunt — Remastered | Intruder | Lethal Company |
| **type** | `game` | `game` | `game` |
| **is_free** | `False` | `False` | `False` |
| **release_date** | `May 18, 2015` | `Mar 1, 2019` | `Oct 23, 2023` |
| **coming_soon** | `False` | `False` | `False` |
| **price_initial_usd** | `49.99` | `19.99` | `9.99` |
| **price_final_usd** | `49.99` | `19.99` | `9.99` |
| **discount_percent** | `0` | `0` | `0` |
| **positive_reviews** | `802,993` | `5,956` | `473,422` |
| **negative_reviews** | `32,356` | `627` | `13,738` |
| **total_recommendations** | `852,279` | `5,447` | `412,199` |
| **owners_range** | `20,000,000 .. 50,000,000` | `200,000 .. 500,000` | `10,000,000 .. 20,000,000` |
| **ccu** | `15,893` | `9` | `6,199` |
| **metacritic_score** | `93.0` | `NaN` | `NaN` |
| **required_age** | `17` | `0` | `0` |
| **developers** | `CD PROJEKT RED` | `Superboss Games` | `Zeekerss` |
| **publishers** | `CD PROJEKT RED` | `Superboss Games` | `Zeekerss` |
| **genres** | `RPG` | `Early Access` | `Action, Adventure, Indie, Early Access` |

---

## 2. Warstwa Silver (Cleaned & Feature Engineered)

*Dane przekształcone w środowisku DuckDB. Odrzucono obiekty nienależące do gier oraz programy użytkowe.*

### A. Cechy podstawowe i czyszczenie
* **`release_date`** (`DATE`): Natywny typ daty. Niepoprawne formaty konwertowane są na `NULL`.
* **`price_initial_usd` / `price_final_usd`** (`DOUBLE`): Ceny oczyszczone. Wycofane ze sprzedaży pozycje z błędnym zerem przyjmują wartość `NULL`.
* **`is_delisted_or_bundled`** (`BOOLEAN`): Flaga określająca brak ceny dla produktów płatnych. Brakujące wartości konwertowane na `FALSE`.
* **`developers` / `publishers`** (`VARCHAR`): Puste stringi zamienione na `NULL`.

### B. Metryki jakości i ekonomiczne
* **`total_reviews`** (`INTEGER`): Suma recenzji (`positive_reviews + negative_reviews`).
* **`positive_ratio`** (`DOUBLE`): Stosunek recenzji pozytywnych do wszystkich (`0.0–1.0`).
* **`wilson_score`** (`DOUBLE`): Dolna granica przedziału ufności Wilsona dla proporcji recenzji pozytywnych [1].
* **`owners_midpoint`** (`BIGINT`): Środek przedziału posiadaczy ze SteamSpy.
* **`estimated_revenue_usd`** (`DOUBLE`): Szacowany przychód wyliczony metodą Boxleitera [2]. Dla produktów bez ceny przyjmuje `NULL`.
* **`game_age_days`** (`INTEGER`): Wiek produktu w dniach.
* **`reviews_per_day`** (`DOUBLE`): Średnie tempo pozyskiwania recenzji w czasie.
* **`ccu_per_1k_reviews`** (`DOUBLE`): Współczynnik aktywności użytkowników.

### C. Transformacje pod modele ML
* **`log_total_reviews` / `log_ccu` / `log_price_usd`** (`DOUBLE`): Zmienne po transformacji logarytmicznej `LN(x + 1)`.
* **`genres_list` / `categories_list`** (`VARCHAR[]`): Tablice napisów. Brakujące elementy mapowane na puste tablice `[]`.
* **`primary_genre`** (`VARCHAR`): Główny gatunek gry. Braki konwertowane na `NULL`.
* **Flagi binarne cech (`is_indie`, `is_early_access`, `is_singleplayer`, `is_multiplayer`, `is_coop`, `is_pvp`, `has_controller_support`, `has_steam_workshop`, `is_vr_supported`)** (`BOOLEAN`): Cechy logiczne. Brakujące dane mapowane na `FALSE` przy użyciu `COALESCE`.
* **`is_self_published`** (`BOOLEAN`): Określa tożsamość dewelopera i wydawcy. Zwraca `NULL` w przypadku braków danych źródłowych.

### D. Kontekst rynkowy
* **`genre_releases_in_year`** (`INTEGER`): Liczba gier w tym samym gatunku wydanych w danym roku.
* **`price_to_genre_median_ratio`** (`DOUBLE`): Stosunek ceny gry do mediany cen w jej gatunku. Brakujące ceny skutkują wartością `NULL`.

### E. Zmienne celu
* **`target_log_revenue_per_day`** (`DOUBLE`): Zlogarytmowany dzienny przychód znormalizowany o wiek. Brakujące przychody dają `NULL`.
* **`target_unmet_demand_score`** (`DOUBLE`): Wskaźnik niezaspokojonego popytu (popyt pomnożony przez wskaźnik niezadowolenia).
* **`target_is_commercial_hit`** (`BOOLEAN`): Flaga sukcesu komercyjnego ($\ge 1000$ recenzji).
* **`target_is_hidden_gem`** (`BOOLEAN`): Flaga ukrytego diamentu (niezależna gra bez mediów z wysokim wskaźnikiem Wilsona).
* **`target_is_evergreen`** (`BOOLEAN`): Flaga długofalowego zaangażowania (wiek $> 365$ dni i CCU $\ge 50$).

| Przetworzona Cecha / Target | The Witcher 3 (292030) | Intruder (518150) | Lethal Company (1966720) |
| :--- | :--- | :--- | :--- |
| **release_date** | `2015-05-18` | `2019-03-01` | `2023-10-23` |
| **release_year** | `2015` | `2019` | `2023` |
| **game_age_days** | `4,198` | `2,815` | `1,118` |
| **total_reviews** | `835,349` | `6,583` | `487,160` |
| **positive_ratio** | `0.9613` | `0.9048` | `0.9718` |
| **wilson_score** | `0.9609` | `0.8974` | `0.9713` |
| **owners_midpoint** | `35,000,000` | `350,000` | `15,000,000` |
| **estimated_revenue_usd** | `$876,941,026.71` | `$2,763,477.57` | `$102,201,296.40` |
| **log_total_reviews** | `13.6356` | `8.7924` | `13.0963` |
| **log_ccu** | `9.6737` | `2.3026` | `8.7323` |
| **primary_genre** | `RPG` | `Early Access` | `Action` |
| **is_indie** | `False` | `False` | `True` |
| **is_coop** | `False` | `False` | `True` |
| **is_self_published** | `True` | `True` | `True` |
| **reviews_per_day** | `198.99` | `2.34` | `435.74` |
| **target_log_revenue_per_day** | `12.25` | `6.89` | `11.42` |
| **target_unmet_demand_score** | `0.53` | `0.84` | `0.37` |
| **target_is_commercial_hit** | `True` | `True` | `True` |
| **target_is_hidden_gem** | `False` | `False` | `True` |
| **target_is_evergreen** | `True` | `False` | `True` |

---

## 3. Przypisy i Metodologia

### [1] Przedział ufności Wilsona (`wilson_score`)
* **Czym to jest:** Metoda statystyczna służąca do obliczania dolnej granicy przedziału ufności dla proporcji w próbie Bernoulliego (w tym przypadku: stosunku ocen pozytywnych do wszystkich ocen).
* **Dlaczego się stosuje:** Tradycyjny wskaźnik procentowy (`positive_ratio`) jest podatny na błąd małej próby (np. gra z dwiema recenzjami i jedną pozytywną ma wynik 100%, co statystycznie jest niemiarodajne). Wzór Wilsona uwzględnia wielkość próby, zaniżając wynik dla małej liczby recenzji na rzecz statystycznej pewności.
* **Gdzie:** Stosowany w systemach rankingowych (m.in. SteamDB, Reddit) do porządkowania obiektów o skrajnie różnej liczbie oddanych głosów.

_How Not To Sort By Average Rating – Evan Miller https://www.evanmiller.org/how-not-to-sort-by-average-rating.html_

### [2] Metoda Boxleitera (`estimated_revenue_usd`)
* **Czym to jest:** Empiryczna metoda szacowania przychodów finansowych gier na platformie Steam, opracowana przez analityka industry-gamedev Chrisa Boxleitera.
* **Dlaczego się stosuje:** Platforma Steam nie publikuje jawnych danych o sprzedaży ani przychodach. Metoda ta opiera się na stałym współczynniku konwersji (zakładającym średnio 1 zakup na każde 30 recenzji użytkowników), cenie początkowej oraz korekcie uwzględniającej prowizję platformy i podatki.
* **Gdzie:** Stosowana w inżynierii danych i analizie rynkowej w sektorze gier wideo do makroekonomicznych szacunków wielkości rynku i potencjału finansowego nisz.

_Boxleiter Method: Steam Sales Multipliers Explained (2026) https://www.steampageanalyzer.com/blog/boxleiter-method-explained_