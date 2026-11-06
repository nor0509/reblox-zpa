Moduł inżynierii danych realizujący pobieranie danych z API SteamSpy oraz Steam Storefront, zapis punktów kontrolnych w bazie SQLite oraz eksport wynikowych zbiorów danych do formatu Apache Parquet pod eksploracyjną analizę danych (EDA).

## Uruchomienie

```bash
cp .env.example .env
# Uruchomienie pełnego cyklu (Discover -> Filter -> Enrich -> Export) w tle:
docker compose up --build -d

# Podgląd logów:
docker compose logs -f

# Sprawdzenie statusu kolejki w bazie SQLite:
docker compose run --rm ingestion-worker status
```

```python

import pandas as pd

df_games = pd.read_parquet("data/processed/games.parquet")
df_tags = pd.read_parquet("data/processed/tags.parquet")

############################################################
import polars as pl

df_games = pl.read_parquet("data/processed/games.parquet")
df_tags = pl.read_parquet("data/processed/tags.parquet")
```