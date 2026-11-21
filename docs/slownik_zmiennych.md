# SteamNicheFinder — Słownik danych

Dokumentacja zmiennych projektu **SteamNicheFinder**. Dane podzielono na warstwę **Bronze** (surowy eksport z API) oraz **Silver** (zbiór oczyszczony, bezstanowy, gotowy pod analizę nisz i modele ML).

## Spis treści

1. [Warstwa Bronze](#1-warstwa-bronze)
2. [Warstwa Silver](#2-warstwa-silver)
   - [A. Dane podstawowe i oczyszczone](#a-dane-podstawowe-i-oczyszczone)
   - [B. Metryki czasu, jakości i ekonomiczne](#b-metryki-czasu-jakości-i-ekonomiczne)
   - [C. Transformacje pod ML i flagi binarne](#c-transformacje-pod-ml-i-flagi-binarne)
   - [D. Zmienne celu](#d-zmienne-celu)
3. [Metodologia i przypisy](#3-metodologia-i-przypisy)

---

## 1. Warstwa Bronze

Dane źródłowe pobrane z API SteamSpy oraz Steam Store, zapisane w bazie SQLite i wyeksportowane do pliku `games.parquet`.

1. **`app_id`** (`INTEGER`) — identyfikator gry na Steam, klucz główny.
2. **`name`** (`VARCHAR`) — tytuł gry; zdarzają się puste ciągi znaków.
3. **`type`** (`VARCHAR`) — typ obiektu w sklepie Steam (np. `game`).
4. **`is_free`** (`BOOLEAN`) — flaga gry darmowej.
5. **`release_date`** (`VARCHAR`) — surowa data premiery w formie tekstu; występują braki i różne formaty.
6. **`coming_soon`** (`BOOLEAN`) — flaga gry przed premierą.
7. **`price_initial_usd` / `price_final_usd`** (`DOUBLE`) — cena katalogowa i końcowa w USD (`0.0` dla gier darmowych).
8. **`discount_percent`** (`INTEGER`) — aktualna zniżka procentowa.
9. **`positive_reviews` / `negative_reviews`** (`INTEGER`) — liczba recenzji pozytywnych i negatywnych.
10. **`total_recommendations`** (`INTEGER`) — liczba rekomendacji w sklepie Steam.
11. **`owners_range`** (`VARCHAR`) — przedział liczby posiadaczy ze SteamSpy (np. `0 .. 20,000`).
12. **`ccu`** (`INTEGER`) — liczba graczy na moment pobrania danych 
13. **`metacritic_score`** (`INTEGER`) — ocena krytyków 0–100; obecna w ~17% rekordów, w pozostałych `NULL`.
14. **`required_age`** (`INTEGER`) — minimalny wiek gracza.
15. **`windows` / `mac` / `linux`** (`BOOLEAN`) — flagi wspieranych systemów operacyjnych.
16. **`developers` / `publishers`** (`VARCHAR`) — listy twórców i wydawców rozdzielone przecinkami; występują puste stringi.
17. **`genres` / `categories`** (`VARCHAR`) — listy gatunków i kategorii rozdzielone przecinkami; występują puste stringi.
18. **`short_description`** (`VARCHAR`) — krótki opis gry ze sklepu; zdarzają się braki.

### Przykładowe rekordy

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

## 2. Warstwa Silver

Dane przetworzone w DuckDB i zapisane do `games_silver.parquet` z kompresją ZSTD (58 kolumn). Wszystkie transformacje są liczone wyłącznie na poziomie pojedynczego wiersza, bez agregacji po całym zbiorze, co wyklucza wyciek danych przy podziale na zbiór treningowy i testowy.

**Zastosowane filtry:**
- wyłącznie gry (`type = 'game'`) po premierze (`coming_soon = FALSE`),
- niepusty tytuł oraz co najmniej jedna recenzja (`total_reviews > 0`),
- odrzucone programy użytkowe (m.in. `Utilities`, `Design & Illustration`, `Video/Audio Production`, `Animation & Modeling`, `Software Training`, `Photo Editing`, `Accounting`, `Web Publishing`).

Kolumny `type`, `coming_soon` oraz `owners_range` zostały usunięte, a `genres` i `categories` przemianowane na `genres_str` i `categories_str`.

### A. Dane podstawowe i oczyszczone

- **`app_id`** (`INTEGER`) — identyfikator gry na Steam, klucz główny.
- **`name`** (`VARCHAR`) — oczyszczony tytuł gry (`TRIM`).
- **`is_free`** (`BOOLEAN`) — skorygowana flaga gry darmowej (`TRUE`, gdy źródłowe `is_free = TRUE` lub w `genres` występuje `Free To Play`).
- **`is_delisted_or_bundled`** (`BOOLEAN`) — gry płatne bez ceny (`is_free = FALSE`, brak tagu `Free To Play`, `price_initial_usd = 0.0`), zwykle wycofane ze sprzedaży lub dostępne wyłącznie w pakietach.
- **`release_date`** (`DATE`) — data premiery sparsowana z formatów `%d %b, %Y`, `%b %d, %Y` i `%b %Y`; błędne lub brakujące wpisy przyjmują `NULL`.
- **`price_initial_usd` / `price_final_usd`** (`DOUBLE`) — ceny w USD; dla gier darmowych `0.0`, dla wycofanych lub pakietowych `NULL`.
- **`discount_percent`** (`INTEGER`) — zniżka procentowa.
- **`positive_reviews` / `negative_reviews`** (`INTEGER`) — liczba recenzji pozytywnych i negatywnych.
- **`total_recommendations`** (`INTEGER`) — liczba rekomendacji; wartości `0` zamienione na `NULL`.
- **`ccu`** (`INTEGER`) — szczytowa liczba graczy jednocześnie.
- **`owners_min` / `owners_max`** (`BIGINT`) — dolna i górna granica przedziału posiadaczy wyciągnięta z `owners_range`.
- **`metacritic_score`** (`INTEGER`) — ocena krytyków 0–100 (`NULL` przy braku oceny).
- **`has_metacritic`** (`BOOLEAN`) — czy gra posiada ocenę w serwisie Metacritic.
- **`required_age`** (`INTEGER`) — minimalny wiek gracza.
- **`windows` / `mac` / `linux`** (`BOOLEAN`) — flagi wspieranych systemów operacyjnych.
- **`platforms_count`** (`INTEGER`) — liczba wspieranych platform (`0–3`).
- **`developers` / `publishers`** (`VARCHAR`) — oczyszczone listy twórców i wydawców; puste stringi zamienione na `NULL`.
- **`genres_str` / `categories_str`** (`VARCHAR`) — oczyszczone ciągi gatunków i kategorii; puste stringi zamienione na `NULL`.
- **`short_description`** (`VARCHAR`) — oczyszczony opis gry; puste stringi zamienione na `NULL`.

### B. Metryki czasu, jakości i ekonomiczne

- **`release_year`** (`BIGINT`) — rok premiery.
- **`release_month`** (`BIGINT`) — miesiąc premiery (`1–12`).
- **`game_age_days`** (`BIGINT`) — wiek gry w dniach względem daty uruchomienia pipeline'u (minimum `1`).
- **`total_reviews`** (`INTEGER`) — suma recenzji (`positive_reviews + negative_reviews`).
- **`positive_ratio`** (`DOUBLE`) — udział recenzji pozytywnych (`0.0–1.0`, zaokrąglony do 4 miejsc).
- **`pos_neg_ratio`** (`DOUBLE`) — stosunek recenzji pozytywnych do negatywnych z wygładzeniem: `positive_reviews / (negative_reviews + 1)`.
- **`wilson_score`** (`DOUBLE`) — dolna granica 95% przedziału ufności Wilsona ($z = 1.96$) dla proporcji ocen pozytywnych [1].
- **`owners_midpoint`** (`BIGINT`) — środek przedziału posiadaczy: `(owners_min + owners_max) / 2`.
- **`estimated_revenue_usd`** (`DOUBLE`) — szacowany przychód netto metodą Boxleitera: `total_reviews * 30.0 * price_initial_usd * 0.7` [2]; `NULL` przy braku ceny.
- **`reviews_per_day`** (`DOUBLE`) — średnie tempo przyrostu recenzji: `total_reviews / game_age_days`.
- **`ccu_per_1k_reviews`** (`DOUBLE`) — wskaźnik bieżącej aktywności graczy: `(ccu / total_reviews) * 1000`.

### C. Transformacje pod ML i flagi binarne

- **`log_total_reviews` / `log_ccu` / `log_price_usd`** (`DOUBLE`) — transformacja $\ln(x + 1)$ ograniczająca skośność rozkładu.
- **`genres_list` / `categories_list`** (`VARCHAR[]`) — tablice gatunków i kategorii powstałe z podziału `genres_str` i `categories_str` po `', '`; braki mapowane na `[]`.
- **`primary_genre`** (`VARCHAR`) — pierwszy gatunek z `genres_str` (`NULL` przy braku danych).
- **`is_indie`**, **`is_early_access`**, **`is_singleplayer`**, **`is_multiplayer`**, **`is_coop`**, **`is_pvp`**, **`has_controller_support`**, **`has_steam_workshop`**, **`is_vr_supported`** (`BOOLEAN`) — flagi binarne cech wyciągnięte z `genres_str` i `categories_str`; braki mapowane na `FALSE`.
- **`is_self_published`** (`BOOLEAN`) — czy deweloper jest jednocześnie wydawcą (`developers = publishers`); `NULL`, gdy brakuje którejś z wartości.

### D. Zmienne celu

- **`target_log_revenue_per_day`** (`DOUBLE`) — zlogarytmowany dzienny przychód znormalizowany o wiek gry: `LN((estimated_revenue_usd / game_age_days) + 1)`.
- **`target_unmet_demand_score`** (`DOUBLE`) — wskaźnik niezaspokojonego popytu łączący wolumen z niezadowoleniem graczy: `LN(total_reviews + 1) * (1.0 - positive_ratio)`.
- **`target_is_commercial_hit`** (`BOOLEAN`) — sukces komercyjny: gra płatna, dostępna w sprzedaży (`NOT is_free AND NOT is_delisted_or_bundled`) z `total_reviews >= 1000`.
- **`target_is_hidden_gem`** (`BOOLEAN`) — ukryta perełka: `is_indie = TRUE`, `has_metacritic = FALSE`, `wilson_score >= 0.85` oraz `reviews_per_day >= 1.0`.
- **`target_is_evergreen`** (`BOOLEAN`) — długofalowe zaangażowanie: `game_age_days > 365` oraz `ccu >= 50`.

### Przykładowe rekordy

| Kolumna | The Witcher 3 (292030) | Intruder (518150) | Lethal Company (1966720) |
| :--- | :--- | :--- | :--- |
| **app_id** | `292030` | `518150` | `1966720` |
| **name** | The Witcher 3: Wild Hunt — Remastered | Intruder | Lethal Company |
| **is_free** | `False` | `False` | `False` |
| **is_delisted_or_bundled** | `False` | `False` | `False` |
| **release_date** | `2015-05-18` | `2019-03-01` | `2023-10-23` |
| **price_initial_usd** | `49.99` | `19.99` | `9.99` |
| **price_final_usd** | `49.99` | `19.99` | `9.99` |
| **discount_percent** | `0` | `0` | `0` |
| **positive_reviews** | `802,993` | `5,956` | `473,422` |
| **negative_reviews** | `32,356` | `627` | `13,738` |
| **total_reviews** | `835,349` | `6,583` | `487,160` |
| **total_recommendations** | `852,279` | `5,447` | `412,199` |
| **ccu** | `15,893` | `9` | `6,199` |
| **owners_min** | `20,000,000` | `200,000` | `10,000,000` |
| **owners_max** | `50,000,000` | `500,000` | `20,000,000` |
| **metacritic_score** | `93` | `NULL` | `NULL` |
| **has_metacritic** | `True` | `False` | `False` |
| **required_age** | `17` | `0` | `0` |
| **windows** | `True` | `True` | `True` |
| **mac** | `False` | `True` | `False` |
| **linux** | `False` | `False` | `False` |
| **platforms_count** | `1` | `2` | `1` |
| **developers** | `CD PROJEKT RED` | `Superboss Games` | `Zeekerss` |
| **publishers** | `CD PROJEKT RED` | `Superboss Games` | `Zeekerss` |
| **genres_str** | `RPG` | `Early Access` | `Action, Adventure, Indie, Early Access` |
| **categories_str** | `Single-player, Steam Achievements, Steam Tradi...` | `Multi-player, PvP, Online PvP, Steam Workshop,...` | `Single-player, Multi-player, Co-op, Online Co-...` |
| **short_description** | `The Witcher 3: Wild Hunt — Remastered moderniz...` | `The ultimate spy-vs-guards simulator. Carefull...` | `A co-op horror about scavenging at abandoned m...` |
| **release_year** | `2015` | `2019` | `2023` |
| **release_month** | `5` | `3` | `10` |
| **game_age_days** | `4,204` | `2,821` | `1,124` |
| **positive_ratio** | `0.9613` | `0.9048` | `0.9718` |
| **pos_neg_ratio** | `24.82` | `9.48` | `34.46` |
| **wilson_score** | `0.9609` | `0.8974` | `0.9713` |
| **owners_midpoint** | `35,000,000` | `350,000` | `15,000,000` |
| **estimated_revenue_usd** | `876,941,026.71 USD` | `2,763,477.57 USD` | `102,201,296.40 USD` |
| **log_total_reviews** | `13.6356` | `8.7924` | `13.0963` |
| **log_ccu** | `9.6737` | `2.3026` | `8.7323` |
| **log_price_usd** | `3.9316` | `3.0440` | `2.3970` |
| **genres_list** | `[RPG]` | `[Early Access]` | `[Action, Adventure, Indie, Early Access]` |
| **primary_genre** | `RPG` | `Early Access` | `Action` |
| **categories_list** | `[Single-player, Steam Achievements, Steam Trad...]` | `[Multi-player, PvP, Online PvP, Steam Workshop...]` | `[Single-player, Multi-player, Co-op, Online Co...]` |
| **is_indie** | `False` | `False` | `True` |
| **is_early_access** | `False` | `True` | `True` |
| **is_singleplayer** | `True` | `False` | `True` |
| **is_multiplayer** | `False` | `True` | `True` |
| **is_coop** | `False` | `False` | `True` |
| **is_pvp** | `False` | `True` | `False` |
| **has_controller_support** | `True` | `False` | `True` |
| **has_steam_workshop** | `True` | `True` | `False` |
| **is_vr_supported** | `False` | `False` | `False` |
| **is_self_published** | `True` | `True` | `True` |
| **reviews_per_day** | `198.7034` | `2.3336` | `433.4164` |
| **ccu_per_1k_reviews** | `19.0256` | `1.3672` | `12.7248` |
| **target_log_revenue_per_day** | `12.2482` | `6.8882` | `11.4178` |
| **target_unmet_demand_score** | `0.5277` | `0.8370` | `0.3693` |
| **target_is_commercial_hit** | `True` | `True` | `True` |
| **target_is_hidden_gem** | `False` | `False` | `True` |
| **target_is_evergreen** | `True` | `False` | `True` |

---

## 3. Metodologia i przypisy

### [1] Przedział ufności Wilsona (`wilson_score`)

Dolna granica przedziału ufności dla proporcji w próbie Bernoulliego przy poziomie ufności 95% ($z = 1.96$). Zwykły odsetek pozytywnych ocen (`positive_ratio`) faworyzuje gry z małą liczbą recenzji (np. 2/2 daje 100%). Wzór Wilsona koryguje ocenę w dół przy małej próbie, co pozwala rzetelnie porównywać tytuły o różnej skali popularności. Rozwiązanie stosowane m.in. w SteamDB i na Reddicie.

Źródło: [How Not To Sort By Average Rating — Evan Miller](https://www.evanmiller.org/how-not-to-sort-by-average-rating.html)

### [2] Metoda Boxleitera (`estimated_revenue_usd`)

Empiryczny sposób szacowania przychodów na Steam, gdzie oficjalne dane sprzedażowe nie są publiczne. Zakłada stały mnożnik konwersji (średnio 30 sprzedanych kopii na 1 recenzję), cenę katalogową oraz współczynnik `0.7` uwzględniający 30% prowizji platformy Steam.

Źródło: [Boxleiter Method: Steam Sales Multipliers Explained (2026)](https://www.steampageanalyzer.com/blog/boxleiter-method-explained)
