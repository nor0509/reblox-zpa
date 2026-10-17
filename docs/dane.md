| Źródło / URL / API | Format | Metoda pobrania | Kto odpowiada | Termin (próbka) |
| :--- | :--- | :--- | :--- | :--- |
| **Steam API** (`store.steampowered.com/api/`) | JSON | `requests` / REST API | Norbert K. | 17.10.2026 |
| **SteamSpy API** (`steamspy.com/api.php`) | JSON | `requests` / REST API | Norbert K. | 17.10.2026 |

## Opis próbek danych z 17.10.2026r

### 1. Podstawowe identyfikatory i metadane
* **`app_id`** *(string)* – Unikalny identyfikator aplikacji w sklepie Steam (np. `"105600"` dla *Terrarii*).
* **`name`** *(string)* – Tytuł gry.
* **`type`** *(string)* – Typ zawartości na platformie (np. `"game"`).
* **`release_date`** *(string)* – Data oficjalnej premiery na Steam.

### 2. Statystyki sprzedaży i zaangażowania graczy
* **`owners`** *(string)* – Szacowany przedział liczby posiadaczy gry (dane pochodzące z *SteamSpy*).
* **`positive`** *(integer)* – Łączna liczba pozytywnych recenzji użytkowników.
* **`negative`** *(integer)* – Łączna liczba negatywnych recenzji użytkowników.
* **`ccu`** *(integer)* – Liczba graczy zalogowanych jednocześnie w danym momencie (*Concurrent Users*).
* **`average_forever`** *(integer)* – Średni skumulowany czas gry na użytkownika (w minutach).
* **`metacritic`** *(integer)* – Średnia ocen krytyków w serwisie Metacritic (skala 0–100).

### 3. Informacje finansowe
* **`base_price`** *(float)* – Podstawowa cena katalogowa gry w walucie bazowej (USD).
* **`is_free`** *(boolean)* – Flaga określająca, czy tytuł jest darmowy (`true`/`false`).

### 4. Tagi społeczności (`tags`)
* **`tags`** *(object)* – Słownik par `klucz: wartość`, gdzie kluczem jest nazwa tagu/gatunku, a wartością liczba głosów oddanych przez społeczność Steam. Pozwala na precyzyjną analizę nisz rynkowych oraz profilu rozgrywki.

### 5. Cechy techniczne i wsparcie językowe
* **`categories`** *(array of strings)* – Lista cech funkcjonalnych gry (np. *Single-player*, *Co-op*, *Steam Workshop*, wsparcie dla kontrolerów, chmura Steam).
* **`supported_languages`** *(array of strings)* – Lista obsługiwanych wersji językowych (z oznaczeniem opcji pełnego dubbingu/audio).
